-- =====================================================================
-- Row Level Security + database API functions.
--
-- Two kinds of callers:
--  1. Humans (dashboard) — signed in with Supabase Auth, role `authenticated`.
--     They see/modify rows of studies they are members of (RLS below).
--  2. Devices (eyetrack laptop, wrist hub, gait rig) — NOT signed in.
--     They call SECURITY DEFINER functions with their device key. The
--     function checks the key hash and only ever writes into that
--     device's own study. Devices cannot read anything.
-- The service-role key is never needed by the web app.
-- =====================================================================

-- Anonymous callers get no direct table access at all.
revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;
grant select, insert, update, delete on all tables in schema public to authenticated;
grant usage on all sequences in schema public to authenticated;

alter table public.profiles            enable row level security;
alter table public.studies             enable row level security;
alter table public.study_members       enable row level security;
alter table public.participants        enable row level security;
alter table public.consents            enable row level security;
alter table public.devices             enable row level security;
alter table public.assessment_sessions enable row level security;
alter table public.recordings          enable row level security;
alter table public.measurements        enable row level security;
alter table public.session_events      enable row level security;
alter table public.predictions         enable row level security;
alter table public.reports             enable row level security;

-- profiles: see yourself and people you share a study with; edit yourself.
create policy profiles_select on public.profiles for select to authenticated using (
  id = auth.uid() or exists (
    select 1 from public.study_members a join public.study_members b on a.study_id = b.study_id
    where a.user_id = auth.uid() and b.user_id = profiles.id));
create policy profiles_update on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

-- studies
create policy studies_select on public.studies for select to authenticated
  using (public.is_study_member(id) or created_by = auth.uid());
create policy studies_insert on public.studies for insert to authenticated
  with check (created_by = auth.uid());
create policy studies_update on public.studies for update to authenticated
  using (public.is_study_member(id, 'owner'));
create policy studies_delete on public.studies for delete to authenticated
  using (public.is_study_member(id, 'owner'));

-- study_members: members can see the roster; only owners change it.
create policy members_select on public.study_members for select to authenticated
  using (public.is_study_member(study_id));
create policy members_write on public.study_members for all to authenticated
  using (public.is_study_member(study_id, 'owner'))
  with check (public.is_study_member(study_id, 'owner'));

-- devices: researchers manage them (keys are created via create_device()).
create policy devices_select on public.devices for select to authenticated
  using (public.is_study_member(study_id, 'researcher'));
create policy devices_update on public.devices for update to authenticated
  using (public.is_study_member(study_id, 'researcher'));
create policy devices_delete on public.devices for delete to authenticated
  using (public.is_study_member(study_id, 'owner'));
-- (no insert policy: devices are created only through create_device())

-- Data tables share one pattern: viewers read, researchers write, owners delete.
do $$
declare t text;
begin
  foreach t in array array['participants','consents','assessment_sessions','recordings',
                           'measurements','session_events','predictions','reports'] loop
    execute format('create policy %1$s_select on public.%1$s for select to authenticated
                      using (public.is_study_member(study_id))', t);
    execute format('create policy %1$s_insert on public.%1$s for insert to authenticated
                      with check (public.is_study_member(study_id, ''researcher''))', t);
    execute format('create policy %1$s_update on public.%1$s for update to authenticated
                      using (public.is_study_member(study_id, ''researcher''))
                      with check (public.is_study_member(study_id, ''researcher''))', t);
    execute format('create policy %1$s_delete on public.%1$s for delete to authenticated
                      using (public.is_study_member(study_id, ''owner''))', t);
  end loop;
end $$;

-- ---------- read model: one row per session ------------------------------
-- security_invoker = the caller's RLS applies, so the view leaks nothing.
create view public.session_overview with (security_invoker = true) as
select s.id as session_id, s.study_id, s.participant_id, p.code as participant_code,
       p.cohort, p.is_synthetic, s.protocol, s.status, s.started_at, s.ended_at,
       coalesce(array_agg(distinct r.modality::text) filter (where r.id is not null), '{}'::text[]) as modalities,
       count(distinct r.id) as n_recordings,
       (select count(*) from public.measurements m where m.session_id = s.id) as n_measurements,
       (select avg(m.value) from public.measurements m
         where m.session_id = s.id and m.name = 'valid_frame_fraction') as eye_valid_frame_fraction
from public.assessment_sessions s
join public.participants p on p.id = s.participant_id
left join public.recordings r on r.session_id = s.id
group by s.id, p.id;
grant select on public.session_overview to authenticated;

-- ---------- device functions ---------------------------------------------
revoke execute on all functions in schema public from public;
grant execute on function public.is_study_member(uuid, public.study_role) to authenticated;

-- Create a device and return its key ONCE. Only the hash is stored.
create or replace function public.create_device(
  p_study_id uuid, p_name text, p_modality public.modality, p_hardware jsonb default '{}'::jsonb)
returns table (device_id uuid, device_key text)
language plpgsql security definer set search_path = ''
as $$
declare k text; d uuid;
begin
  if not public.is_study_member(p_study_id, 'researcher') then
    raise exception 'not a researcher in this study' using errcode = '42501';
  end if;
  -- 2 x UUIDv4 = 244 random bits, using only built-in functions.
  k := 'dk_' || replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '');
  insert into public.devices (study_id, name, modality, hardware, key_hash, key_prefix)
  values (p_study_id, p_name, p_modality, coalesce(p_hardware, '{}'::jsonb),
          sha256(convert_to(k, 'UTF8')), left(k, 10))
  returning id into d;
  return query select d, k;
end $$;
grant execute on function public.create_device(uuid, text, public.modality, jsonb) to authenticated;

create or replace function public._device_for_key(p_key text)
returns public.devices
language plpgsql stable security definer set search_path = ''
as $$
declare d public.devices;
begin
  select * into d from public.devices
   where key_hash = sha256(convert_to(coalesce(p_key, ''), 'UTF8')) and revoked_at is null;
  if d.id is null then
    raise exception 'invalid or revoked device key' using errcode = '28000';
  end if;
  return d;
end $$;
-- internal only: no grant

create or replace function public.device_create_session(
  p_device_key text, p_participant_code text, p_protocol text default null)
returns uuid
language plpgsql security definer set search_path = ''
as $$
declare d public.devices; pid uuid; sid uuid;
begin
  d := public._device_for_key(p_device_key);
  select id into pid from public.participants where study_id = d.study_id and code = p_participant_code;
  if pid is null then
    raise exception 'unknown participant code in this study' using errcode = 'P0002';
  end if;
  insert into public.assessment_sessions (study_id, participant_id, protocol, created_via, created_by)
  values (d.study_id, pid, p_protocol, 'device', null)
  returning id into sid;
  update public.devices set last_seen_at = now() where id = d.id;
  return sid;
end $$;
grant execute on function public.device_create_session(text, text, text) to anon, authenticated;

-- Ingest one measurement batch (docs/DATA_FORMAT.md). Atomic: all or nothing.
create or replace function public.ingest_batch(p_device_key text, p_batch jsonb)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
  d public.devices;
  sid uuid := (p_batch ->> 'session_id')::uuid;
  rec jsonb := p_batch -> 'recording';
  mod public.modality := (rec ->> 'modality')::public.modality;
  rid uuid;
  n_m int; n_e int;
begin
  d := public._device_for_key(p_device_key);
  if p_batch ->> 'schema_version' is distinct from '1.0' then
    raise exception 'unsupported schema_version' using errcode = '22023';
  end if;
  if not exists (select 1 from public.assessment_sessions where id = sid and study_id = d.study_id) then
    raise exception 'session not found in this device''s study' using errcode = 'P0002';
  end if;
  if d.modality <> 'other' and d.modality <> mod then
    raise exception 'device modality % cannot upload % data', d.modality, mod using errcode = '22023';
  end if;
  if coalesce((rec ->> 'raw_media_stored')::boolean, false) then
    raise exception 'raw media is not accepted through ingest' using errcode = '22023';
  end if;
  if jsonb_array_length(coalesce(p_batch -> 'measurements', '[]')) > 5000
     or jsonb_array_length(coalesce(p_batch -> 'events', '[]')) > 5000 then
    raise exception 'batch too large (max 5000 measurements and 5000 events)' using errcode = '54000';
  end if;

  -- Idempotency: the same device re-sending the same recording returns the original.
  select id into rid from public.recordings
   where device_id = d.id and session_id = sid and started_at = (rec ->> 'started_at')::timestamptz;
  if rid is not null then
    return jsonb_build_object('recording_id', rid, 'duplicate', true);
  end if;

  insert into public.recordings (session_id, study_id, device_id, modality, started_at, ended_at,
      sample_rate_hz, protocol, is_synthetic, clock_offset_ms, clock, device_info, quality, schema_version)
  values (sid, d.study_id, d.id, mod, (rec ->> 'started_at')::timestamptz,
      (rec ->> 'ended_at')::timestamptz, (rec ->> 'sample_rate_hz')::double precision,
      rec ->> 'protocol', coalesce((rec ->> 'is_synthetic')::boolean, false),
      coalesce((rec -> 'clock' ->> 'offset_ms')::double precision, 0),
      coalesce(rec -> 'clock', '{}'), coalesce(rec -> 'device_info', '{}'),
      coalesce(rec -> 'quality', '{}'), p_batch ->> 'schema_version')
  returning id into rid;

  insert into public.measurements (recording_id, session_id, study_id, modality, name, value, unit,
                                   t, task, confidence, quality_flags, metadata)
  select rid, sid, d.study_id, mod, m ->> 'name', (m ->> 'value')::double precision, m ->> 'unit',
         (m ->> 't')::timestamptz, m ->> 'task', (m ->> 'confidence')::real,
         coalesce(array(select jsonb_array_elements_text(m -> 'quality_flags')), '{}'),
         coalesce(m -> 'metadata', '{}')
  from jsonb_array_elements(coalesce(p_batch -> 'measurements', '[]')) m;
  get diagnostics n_m = row_count;

  insert into public.session_events (session_id, study_id, recording_id, t, kind, task, data)
  select sid, d.study_id, rid, (e ->> 't')::timestamptz, e ->> 'kind', e ->> 'task', coalesce(e -> 'data', '{}')
  from jsonb_array_elements(coalesce(p_batch -> 'events', '[]')) e;
  get diagnostics n_e = row_count;

  update public.devices set last_seen_at = now() where id = d.id;
  return jsonb_build_object('recording_id', rid, 'duplicate', false,
                            'n_measurements', n_m, 'n_events', n_e);
end $$;
grant execute on function public.ingest_batch(text, jsonb) to anon, authenticated;

-- ---------- placeholder "model": z-scores vs the study's control cohort ----
-- NOT a diagnostic. For each summary measurement in a session, how many
-- standard deviations it sits from this study's control participants.
-- With synthetic data it is only a plumbing test for the predictions table.
create or replace function public.cohort_zscores(p_session_id uuid)
returns jsonb
language sql stable security invoker set search_path = ''
as $$
  with target as (
    select m.name, avg(m.value) as value from public.measurements m
    where m.session_id = p_session_id and m.t is null group by m.name
  ), ctrl as (
    select m.name, avg(m.value) as mean, stddev_samp(m.value) as sd, count(distinct s.participant_id) as n
    from public.measurements m
    join public.assessment_sessions s on s.id = m.session_id
    join public.participants p on p.id = s.participant_id
    where p.cohort = 'control' and m.t is null and m.session_id <> p_session_id
      and s.study_id = (select study_id from public.assessment_sessions where id = p_session_id)
    group by m.name
  )
  select coalesce(jsonb_object_agg(t.name, jsonb_build_object(
           'value', t.value, 'control_mean', c.mean, 'control_sd', c.sd, 'n_controls', c.n,
           'z', case when c.sd > 0 then (t.value - c.mean) / c.sd end)), '{}'::jsonb)
  from target t join ctrl c on c.name = t.name where c.n >= 2;
$$;
grant execute on function public.cohort_zscores(uuid) to authenticated;
