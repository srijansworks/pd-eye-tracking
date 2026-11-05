# Contributing

## Ground rules
1. **No real participant data in git, ever.** No videos, no names, no recordings folders. `.gitignore`
   blocks the usual paths; double-check `git status` before committing.
2. **No secrets in git.** Copy `.env.example` → `.env.local` / `.env`. Never put a Supabase
   service-role key in the web app or in `NEXT_PUBLIC_*`.
3. **No clinical claims** in code, UI or docs. Say "research measurement", and report quality flags.
4. Every new measurement gets a name in [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md) and a test.

## Workflow
- Branch from `main`: `feat/wrist-ingest`, `fix/blink-merge`, …
- Small commits with a clear message. Open a pull request and ask a teammate to review.
- Before pushing:
  ```bash
  (cd eye-tracking && .venv/bin/python -m pytest -q)
  (cd web && npm test && npx tsc --noEmit)
  ```

## Database changes
- Never edit an applied migration. Add a new file in `supabase/migrations/` named
  `YYYYMMDDHHMMSS_description.sql`.
- New tables need: `study_id`, RLS enabled, policies, and a test in `web/tests/db.test.ts`
  showing that a non-member cannot read them.

## Adding a sensor (wrist, gait)
Follow the checklist at the end of [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md). You don't need any database
change. Your device uploads batches with its own key.
