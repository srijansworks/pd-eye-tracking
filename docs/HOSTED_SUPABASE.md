# Moving the team database to hosted Supabase

The local database (Docker) only lives on one laptop. A hosted Supabase project gives the whole
team one shared database. The free plan is enough. The website still runs on each person's laptop
(`npm run dev`) and talks to the shared database.

**Two rules**
- The **database password** you choose in step 1 is only for you. Store it in a password manager and never paste it into chat, code or git.
- **Never run `supabase/seed.sql` on the hosted project.** It contains a public test login and a public device key.
  `supabase db push` (step 3) applies only the schema, not the seed.

---

## 1. Create the project (in the browser)
1. Go to https://supabase.com/dashboard and sign in ("Continue with GitHub" works).
2. **New project** → organization: your personal one → **Name:** `pd-eye-tracking`.
3. **Database password:** click **Generate a password**, then save it in your password manager.
4. **Region:** `West US (North California)` (closest to the Bay Area). **Plan:** Free.
5. Click **Create new project** and wait about 2 minutes until it says the project is ready.
6. Note your **project ref**: the random ID in the dashboard URL,
   `supabase.com/dashboard/project/<this-part>`.

## 2. Log the CLI in (Terminal, Window 2)
```bash
cd ~/Documents/Projects/pd-eye-tracking
```
```bash
npx supabase login
```
A browser tab opens. Click **Authorize**. Terminal then says you're logged in.

## 3. Push the database schema
Replace `<project-ref>` with the ID from step 1.6:
```bash
npx supabase link --project-ref <project-ref>
```
When asked for the database password, paste it from your password manager. It won't show as you type; that's normal.
```bash
npx supabase db push --remote
```
**Include `--remote`.** If your local Docker database is running, plain `db push` silently targets the *local*
database and says "Local database is up to date". The first line must say `Target: project … · production`.
It lists 3 migrations (`core_schema`, `rls_and_api`, `raw_media_storage`) and **no seeds**. Type `Y`.
**Expected:** `Applying migration …` three times, then `Finished supabase db push.`
Check: `npx supabase migration list --remote` shows all three in the **remote** column.

## 4. Auth settings (browser)
Dashboard → **Authentication** → **URL Configuration**:
- **Site URL:** `http://localhost:3000`
- **Redirect URLs:** add `http://localhost:3000/**`, then **Save**.

The free plan sends only a few sign-up emails per hour. If a teammate never gets their confirmation email,
turn off **Authentication → Sign In / Providers → Email → Confirm email** temporarily.

## 5. Point the website at the hosted database
Dashboard → **Project Settings** → **API Keys** (older dashboards: **API**). Copy the **Project URL**
and the **anon / publishable** key. Both are public by design; the row-level security rules protect the data.
**Never** copy the `service_role` / secret key into the web app.

Keep the local settings as a backup, then write the hosted ones:
```bash
cp web/.env.local web/.env.local.docker
```
```bash
printf "NEXT_PUBLIC_SUPABASE_URL=%s\nNEXT_PUBLIC_SUPABASE_ANON_KEY=%s\n" "PASTE_PROJECT_URL" "PASTE_ANON_KEY" > web/.env.local
```
Restart the website (Window 1: **Ctrl + C**, then):
```bash
npm run dev
```

## 6. Create your account
Open http://localhost:3000 → type your email and a new password → **Create account** → click the link in
the confirmation email. You'll see an empty dashboard. That's correct: you aren't in a study yet.

## 7. Create the team study and your device key
1. Ask each teammate to do step 6 on their own laptop first (step 9 explains their setup).
2. Open `supabase/admin/setup_hosted_study.sql` and replace `OWNER_EMAIL@example.com` with your email and the
   `TEAMMATE…@example.com` placeholders with teammates' emails. Delete teammate entries you don't have yet.
3. Dashboard → **SQL Editor** → **New query** → paste the whole file → **Run**.
4. In the results, **copy `device_key` right away.** It's shown only once.

## 8. Upload from the eye tracker
Create `eye-tracking/.env` (git-ignored) with your key:
```bash
printf "EYETRACK_API_URL=http://localhost:3000\nEYETRACK_DEVICE_KEY=%s\n" "PASTE_DEVICE_KEY" > eye-tracking/.env
```
Test with synthetic data, then your real recording:
```bash
cd eye-tracking && .venv/bin/eyetrack simulate --out recordings/hosted_test --fps 30 && .venv/bin/eyetrack upload recordings/hosted_test --participant SYN-101
```
**Expected:** `"duplicate": false` and the session appears on http://localhost:3000 and in the dashboard's
**Table Editor → assessment_sessions**. Real recordings of yourself go under participant `P001`.

## 9. Teammates
1. Clone the repo, then run `cd web && npm install`.
2. Create `web/.env.local` with the same Project URL and anon key. Send these over your team chat,
   not in git. They're public keys, but keeping them out of git avoids accidental reuse.
3. `npm run dev` → **Create account** → tell the study owner. The owner adds them with:
   ```sql
   insert into public.study_members (study_id, user_id, role)
   select s.id, u.id, 'researcher' from public.studies s, auth.users u
   where s.name = 'Conrad PD pilot' and u.email = 'TEAMMATE@example.com';
   ```
4. Wrist and gait devices: the owner makes one key per device with the step-7 query (change the device
   name and `'eye'` to `'wrist'` or `'gait'`).

## Switching back to the local Docker database
```bash
cp web/.env.local.docker web/.env.local
```
