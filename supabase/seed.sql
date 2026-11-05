-- Synthetic development data. Runs on `supabase db reset` (local only).
-- No real people: every participant is flagged is_synthetic.
-- Creates a dev login:  dev@example.test / devpassword123  (local Supabase only)

insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
                        raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
                        confirmation_token, recovery_token, email_change_token_new, email_change)
values ('00000000-0000-0000-0000-000000000000', '11111111-1111-4111-8111-111111111111',
        'authenticated', 'authenticated', 'dev@example.test',
        crypt('devpassword123', gen_salt('bf')), now(),
        '{"provider":"email","providers":["email"]}', '{"display_name":"Dev Researcher"}',
        now(), now(), '', '', '', '')
on conflict (id) do nothing;

insert into auth.identities (id, user_id, provider_id, identity_data, provider, created_at, updated_at, last_sign_in_at)
values (gen_random_uuid(), '11111111-1111-4111-8111-111111111111', '11111111-1111-4111-8111-111111111111',
        '{"sub":"11111111-1111-4111-8111-111111111111","email":"dev@example.test"}', 'email', now(), now(), now())
on conflict do nothing;

insert into public.studies (id, name, description, created_by)
values ('22222222-2222-4222-8222-222222222222', 'Synthetic dev study',
        'Synthetic data only — for development of the multi-sensor pipeline.',
        '11111111-1111-4111-8111-111111111111')
on conflict (id) do nothing;

insert into public.participants (study_id, code, cohort, is_synthetic) values
  ('22222222-2222-4222-8222-222222222222', 'SYN-001', 'control', true),
  ('22222222-2222-4222-8222-222222222222', 'SYN-002', 'control', true),
  ('22222222-2222-4222-8222-222222222222', 'SYN-003', 'control', true),
  ('22222222-2222-4222-8222-222222222222', 'SYN-101', 'synthetic', true)
on conflict do nothing;

-- A fixed dev device key so the Python CLI works out of the box locally:
--   EYETRACK_DEVICE_KEY=dk_local_dev_eye_key_do_not_use_in_production
insert into public.devices (study_id, name, modality, key_hash, key_prefix)
values ('22222222-2222-4222-8222-222222222222', 'dev laptop webcam', 'eye',
        sha256(convert_to('dk_local_dev_eye_key_do_not_use_in_production', 'UTF8')), 'dk_local_d')
on conflict do nothing;
