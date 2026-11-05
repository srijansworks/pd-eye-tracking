# Backend: architecture, database, API, security

## Architecture

```
 eye laptop (Python eyetrack) ─┐   Bearer dk_… (device key)
 wrist hub (teammate)  ────────┼──▶ Next.js /api/v1/* ──(anon key + rpc)──▶ Postgres function ingest_batch()
 gait rig  (teammate)  ────────┘     (zod validation)                         (checks key hash, writes rows)
                                                                                     │
 researcher browser ──(Supabase Auth cookie)──▶ Next.js pages / GET APIs ──▶ tables via RLS (study membership)
```

**Why this shape**
* **No separate FastAPI service yet.** The Python pipeline runs on the laptop next to the camera
  and uploads *derived* numbers, so there is no server-side inference to host. Add FastAPI only
  when a model needs Python on the server (e.g. a trained classifier over many sessions). It would
  then read and write the same tables and post results to `/api/v1/sessions/:id/predictions`.
* **Authorization lives in Postgres.** RLS for humans, `SECURITY DEFINER` functions for
  devices. The web app never needs the service-role key, so it can't leak from Next.js.
* **The "long" measurements table** (one row per name/value/unit) means teammates add new sensors
  and features without database migrations.

## Database (supabase/migrations)

```
studies ─┬─ study_members (user_id, role: viewer < researcher < owner)
         ├─ participants (pseudonymous code, cohort, is_synthetic) ── consents (raw_video_storage…)
         ├─ devices (modality, key_hash, revoked_at)
         └─ assessment_sessions (participant, protocol, status, started_at)
               ├─ recordings (one per device upload: modality, started_at, sample_rate, clock_offset_ms, quality, raw_media_path?)
               │     ├─ measurements (name, value, unit, t?, task, confidence, quality_flags, metadata)
               │     └─ session_events (t, kind, task, data)   — stimulus onsets, sync taps…
               ├─ predictions (model_name, version, output, is_research_only = true enforced)
               └─ reports (content, storage_path)
view: session_overview (per-session counts, modalities, eye quality), security_invoker
```

Integrity rules enforced in SQL (all tested in `web/tests/db.test.ts`):
* Composite foreign keys stop a session from pointing at a participant in another study, and the same for recordings and measurements.
* `participants.code` must match `^[A-Za-z0-9_-]{2,32}$` (pseudonyms, not names).
* `recordings.raw_media_path` can be set only if the participant has an active `raw_video_storage` consent (trigger).
* `predictions.is_research_only` must be true (check constraint).
* `recordings (device_id, session_id, started_at)` is unique, which makes uploads idempotent.

## API (web/app/api/v1)
| Method & path | Auth | Purpose |
|---|---|---|
| `POST /api/v1/sessions` | device key **or** signed-in researcher (+`study_id`) | Create an assessment session from `participant_code` → `{session_id}` |
| `GET /api/v1/sessions?participant_id=&limit=` | signed in | List sessions (from `session_overview`) |
| `GET /api/v1/sessions/:id` | signed in | Session summary: overview, recordings + quality, summary measurements, predictions |
| `GET /api/v1/sessions/:id/export` | signed in | CSV of all measurements |
| `POST /api/v1/ingest` | device key | Upload one measurement batch ([DATA_FORMAT.md](DATA_FORMAT.md)) |
| `GET /api/v1/participants/:id/measurements?name=&modality=` | signed in | History per measurement across sessions (trends) |
| `GET /api/v1/sessions/:id/predictions` | signed in | Stored model outputs |
| `POST /api/v1/sessions/:id/predictions` | signed in researcher | `{"model":"cohort_zscore_v0"}` runs the placeholder z-score comparison vs this study's controls; `{"model":"external",…}` stores an external model's output |

Errors: `401` bad/missing key or not signed in, `403` not allowed, `404` not found,
`400` validation (with `issues[]`), `413` too large.

Dashboard pages: `/` sessions, `/sessions/:id` recordings + measurements + flags + CSV link,
`/participants/:id` trend sparklines, `/login`.

## Security and privacy checklist
- [x] RLS on every table; anon role has **no** table privileges.
- [x] Device keys: 244-bit random, stored as SHA-256, revocable, scoped to one study and modality, write-only.
- [x] No service-role key in the web app (`.env.example` explains why).
- [x] No raw video by default; raw media only into the private `raw-media` bucket, gated by consent in both table and storage policies.
- [x] Pseudonymous participant codes; synthetic data flagged end-to-end (`is_synthetic`).
- [x] Predictions forced to `is_research_only`.
- [ ] Rate limiting on `/api/v1/ingest` (add on the hosting platform before any public deployment).
- [ ] Ethics/IRB-style approval and consent forms before *any* real participant data.

## Run locally
Requires Docker + the Supabase CLI (`brew install supabase/tap/supabase`).
```bash
supabase init            # once; creates supabase/config.toml, keeps our migrations
supabase start           # local Postgres + Auth + Studio; prints API URL + anon key
supabase db reset        # applies migrations + seed.sql (synthetic study, dev login, dev device key)
cd web && cp .env.example .env.local   # paste the URL + anon key from `supabase status`
npm install && npm run dev             # http://localhost:3000, sign in dev@example.test / devpassword123
```
Tests without Docker: `cd web && npm test` (PGlite runs the real migrations in-process).
