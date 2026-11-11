-- =====================================================================
-- One-time setup for the HOSTED Supabase project.
-- Paste into: Supabase dashboard → SQL Editor → New query → Run.
--
-- Before running:
--   1. Everyone listed below must already have created an account in the
--      web app (Create account on the login page).
--   2. Replace the example emails below (keep the quotes).
--
-- Never run supabase/seed.sql on the hosted project: it contains a public
-- test login and a public device key meant for local development only.
-- =====================================================================

begin;

-- 1. The study, owned by you (the study owner can add/remove members).
insert into public.studies (name, description, created_by)
select 'Conrad PD pilot',
       'Multi-sensor Parkinson''s research prototype (eye, wrist, gait). Not a medical device.',
       id
from auth.users where email = 'OWNER_EMAIL@example.com';   -- ← your email

-- 2. Teammates as researchers (can add participants and sessions; only the owner deletes).
insert into public.study_members (study_id, user_id, role)
select s.id, u.id, 'researcher'
from public.studies s, auth.users u
where s.name = 'Conrad PD pilot'
  and u.email in ('TEAMMATE1@example.com', 'TEAMMATE2@example.com')   -- ← teammates' emails
on conflict do nothing;

-- 3. Pseudonymous participant codes. P001 = first real volunteer (e.g. you);
--    SYN-101 = synthetic data used to test the pipeline.
insert into public.participants (study_id, code, cohort, is_synthetic)
select s.id, x.code, x.cohort, x.syn
from public.studies s,
     (values ('P001', 'unknown', false), ('SYN-101', 'synthetic', true)) as x(code, cohort, syn)
where s.name = 'Conrad PD pilot'
on conflict do nothing;

commit;

-- 4. Device key for the eye-tracking laptop. COPY device_key FROM THE RESULT NOW:
--    only its hash is stored, so it can never be shown again.
--    Put it in eye-tracking/.env as EYETRACK_DEVICE_KEY. Never commit or share it.
with k as materialized (
  select 'dk_' || replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '') as key
), d as (
  insert into public.devices (study_id, name, modality, key_hash, key_prefix)
  select s.id, 'Srijan laptop webcam', 'eye', sha256(convert_to(k.key, 'UTF8')), left(k.key, 10)
  from public.studies s, k
  where s.name = 'Conrad PD pilot'
  returning id, study_id
)
select (select key from k) as device_key, d.id as device_id, d.study_id from d;

-- Check: who is in the study?
select u.email, m.role from public.study_members m
join auth.users u on u.id = m.user_id
join public.studies s on s.id = m.study_id
where s.name = 'Conrad PD pilot';
