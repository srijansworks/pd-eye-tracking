-- =====================================================================
-- Core schema: studies, participants, sessions, multi-sensor recordings,
-- measurements, events, predictions, reports.
--
-- Design rules
--  * Everything belongs to a STUDY. Access = membership in that study.
--  * One ASSESSMENT SESSION = one participant visit. Every device (eye,
--    wrist, gait) uploads its own RECORDING into the same session.
--  * MEASUREMENTS are long/"tidy": one row per (name, value, unit). A new
--    sensor or a new feature needs NO schema change.
--  * No names/emails of participants: only a pseudonymous code.
--  * Raw video is never required; a path may be stored only with consent.
-- =====================================================================

create type public.modality as enum ('eye', 'wrist', 'gait', 'other');
-- Order matters: later = more privileges (used with >= in is_study_member).
create type public.study_role as enum ('viewer', 'researcher', 'owner');

-- ---------- people -------------------------------------------------------
create table public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  created_at   timestamptz not null default now()
);

create table public.studies (
  id          uuid primary key default gen_random_uuid(),
  name        text not null check (char_length(name) between 2 and 120),
  description text,
  created_by  uuid not null default auth.uid() references auth.users (id),
  created_at  timestamptz not null default now()
);

create table public.study_members (
  study_id   uuid not null references public.studies (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  role       public.study_role not null default 'researcher',
  created_at timestamptz not null default now(),
  primary key (study_id, user_id)
);

create table public.participants (
  id           uuid primary key default gen_random_uuid(),
  study_id     uuid not null references public.studies (id) on delete cascade,
  -- Pseudonym only (e.g. P001, SYN-0042). The regex blocks spaces, which
  -- makes it awkward to type a real full name here by accident.
  code         text not null check (code ~ '^[A-Za-z0-9_-]{2,32}$'),
  cohort       text not null default 'unknown'
               check (cohort in ('control', 'pd', 'unknown', 'synthetic')),
  is_synthetic boolean not null default false,
  birth_year   int check (birth_year between 1900 and 2100),
  notes        text,
  created_at   timestamptz not null default now(),
  unique (study_id, code),
  unique (id, study_id)              -- target for composite FKs below
);

create table public.consents (
  id               uuid primary key default gen_random_uuid(),
  study_id         uuid not null,
  participant_id   uuid not null,
  kind             text not null check (kind in ('participation', 'raw_video_storage', 'data_sharing')),
  document_version text,
  granted_at       timestamptz not null default now(),
  revoked_at       timestamptz,
  recorded_by      uuid default auth.uid() references auth.users (id),
  foreign key (participant_id, study_id) references public.participants (id, study_id) on delete cascade
);

-- ---------- devices ------------------------------------------------------
-- A device = one data source (a laptop running eyetrack, a wrist band hub…).
-- It authenticates with a random key; only the SHA-256 hash is stored.
create table public.devices (
  id           uuid primary key default gen_random_uuid(),
  study_id     uuid not null references public.studies (id) on delete cascade,
  name         text not null,
  modality     public.modality not null,
  hardware     jsonb not null default '{}'::jsonb,
  key_hash     bytea not null unique,
  key_prefix   text not null,          -- first chars, so humans can tell keys apart
  created_by   uuid default auth.uid() references auth.users (id),
  created_at   timestamptz not null default now(),
  revoked_at   timestamptz,
  last_seen_at timestamptz,
  unique (id, study_id)
);

-- ---------- sessions & data ---------------------------------------------
create table public.assessment_sessions (
  id             uuid primary key default gen_random_uuid(),
  study_id       uuid not null references public.studies (id) on delete cascade,
  participant_id uuid not null,
  protocol       text,
  status         text not null default 'in_progress'
                 check (status in ('planned', 'in_progress', 'completed', 'aborted')),
  started_at     timestamptz not null default now(),
  ended_at       timestamptz,
  notes          text,
  created_via    text not null default 'dashboard' check (created_via in ('dashboard', 'device', 'seed')),
  created_by     uuid default auth.uid() references auth.users (id),
  created_at     timestamptz not null default now(),
  foreign key (participant_id, study_id) references public.participants (id, study_id) on delete cascade,
  unique (id, study_id)
);
create index on public.assessment_sessions (participant_id, started_at desc);

-- One upload from one device in one session (eye recording, wrist recording…).
create table public.recordings (
  id              uuid primary key default gen_random_uuid(),
  session_id      uuid not null,
  study_id        uuid not null,
  device_id       uuid references public.devices (id) on delete set null,
  modality        public.modality not null,
  started_at      timestamptz not null,
  ended_at        timestamptz,
  sample_rate_hz  double precision,
  protocol        text,
  is_synthetic    boolean not null default false,
  -- Time alignment: device_time + clock_offset_ms = session reference UTC.
  clock_offset_ms double precision not null default 0,
  clock           jsonb not null default '{}'::jsonb,
  device_info     jsonb not null default '{}'::jsonb,
  quality         jsonb not null default '{}'::jsonb,
  raw_media_path  text,                -- Storage path; only allowed with consent (trigger below)
  schema_version  text not null default '1.0',
  created_at      timestamptz not null default now(),
  foreign key (session_id, study_id) references public.assessment_sessions (id, study_id) on delete cascade,
  unique (device_id, session_id, started_at)   -- makes re-uploads idempotent
);
create index on public.recordings (session_id);

create table public.measurements (
  id            bigint generated always as identity primary key,
  recording_id  uuid not null references public.recordings (id) on delete cascade,
  session_id    uuid not null,
  study_id      uuid not null,
  modality      public.modality not null,
  name          text not null check (name ~ '^[a-z][a-z0-9_]{1,63}$'),
  value         double precision not null,
  unit          text not null,
  t             timestamptz,           -- null = summary value for the recording/task
  task          text,
  confidence    real check (confidence between 0 and 1),
  quality_flags text[] not null default '{}',
  metadata      jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now(),
  foreign key (session_id, study_id) references public.assessment_sessions (id, study_id) on delete cascade
);
create index on public.measurements (session_id, name);
create index on public.measurements (study_id, name);

create table public.session_events (
  id           bigint generated always as identity primary key,
  session_id   uuid not null,
  study_id     uuid not null,
  recording_id uuid references public.recordings (id) on delete cascade,
  t            timestamptz not null,
  kind         text not null,
  task         text,
  data         jsonb not null default '{}'::jsonb,
  foreign key (session_id, study_id) references public.assessment_sessions (id, study_id) on delete cascade
);
create index on public.session_events (session_id, t);

create table public.predictions (
  id               uuid primary key default gen_random_uuid(),
  session_id       uuid not null,
  study_id         uuid not null,
  model_name       text not null,
  model_version    text not null,
  output           jsonb not null,
  -- Hard guard: nothing in this system is a validated diagnostic.
  is_research_only boolean not null default true check (is_research_only),
  created_by       uuid default auth.uid() references auth.users (id),
  created_at       timestamptz not null default now(),
  foreign key (session_id, study_id) references public.assessment_sessions (id, study_id) on delete cascade
);

create table public.reports (
  id           uuid primary key default gen_random_uuid(),
  session_id   uuid not null,
  study_id     uuid not null,
  kind         text not null default 'session_summary',
  content      jsonb not null,
  storage_path text,
  created_by   uuid default auth.uid() references auth.users (id),
  created_at   timestamptz not null default now(),
  foreign key (session_id, study_id) references public.assessment_sessions (id, study_id) on delete cascade
);

-- ---------- helpers & triggers ------------------------------------------
create or replace function public.is_study_member(p_study uuid, p_min public.study_role default 'viewer')
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.study_members m
    where m.study_id = p_study and m.user_id = auth.uid() and m.role >= p_min
  );
$$;

-- Creator of a study automatically becomes its owner.
create or replace function public.tg_study_owner() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.study_members (study_id, user_id, role) values (new.id, new.created_by, 'owner');
  return new;
end $$;
create trigger study_owner after insert on public.studies
  for each row execute function public.tg_study_owner();

-- Profile row for every new auth user.
create or replace function public.tg_new_user() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)))
  on conflict do nothing;
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.tg_new_user();

-- Raw media path requires an active raw_video_storage consent.
create or replace function public.tg_raw_media_requires_consent() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  if new.raw_media_path is not null and not exists (
    select 1 from public.consents c
    join public.assessment_sessions s on s.participant_id = c.participant_id
    where s.id = new.session_id and c.kind = 'raw_video_storage' and c.revoked_at is null
  ) then
    raise exception 'raw media requires an active raw_video_storage consent' using errcode = '42501';
  end if;
  return new;
end $$;
create trigger raw_media_consent before insert or update of raw_media_path on public.recordings
  for each row execute function public.tg_raw_media_requires_consent();
