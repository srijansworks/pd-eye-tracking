-- =====================================================================
-- Optional raw-media storage (facial video). OFF by default in the
-- pipeline. A private bucket; objects live at
--   {study_id}/{session_id}/{filename}
-- Researchers of the study may upload/read only if the session's
-- participant has an active raw_video_storage consent.
-- =====================================================================

insert into storage.buckets (id, name, public)
values ('raw-media', 'raw-media', false)
on conflict (id) do nothing;

create or replace function public.can_access_raw_media(p_path text)
returns boolean
language sql stable security definer set search_path = ''
as $$
  select case
    when (storage.foldername(p_path))[1] !~ '^[0-9a-f-]{36}$'
      or (storage.foldername(p_path))[2] !~ '^[0-9a-f-]{36}$' then false
    else public.is_study_member(((storage.foldername(p_path))[1])::uuid, 'researcher')
     and exists (
       select 1 from public.assessment_sessions s
       join public.consents c on c.participant_id = s.participant_id
       where s.id = ((storage.foldername(p_path))[2])::uuid
         and s.study_id = ((storage.foldername(p_path))[1])::uuid
         and c.kind = 'raw_video_storage' and c.revoked_at is null)
  end;
$$;
grant execute on function public.can_access_raw_media(text) to authenticated;

create policy raw_media_read on storage.objects for select to authenticated
  using (bucket_id = 'raw-media' and public.can_access_raw_media(name));
create policy raw_media_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'raw-media' and public.can_access_raw_media(name));
create policy raw_media_delete on storage.objects for delete to authenticated
  using (bucket_id = 'raw-media' and public.can_access_raw_media(name));
