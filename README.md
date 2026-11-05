# Multi-sensor Parkinson's assessment (Conrad Challenge): eye-tracking + backend

> **Research prototype.** Nothing in this repository is clinically validated. It does not
> diagnose, screen for, or predict Parkinson's disease. Development uses **synthetic data only**.

This repo holds the **eye-tracking subsystem** and the **shared backend** that the wrist and gait
subsystems will plug into.

```
Webcam ─▶ eye-tracking/ (Python: MediaPipe iris tracking → eye-movement events → measurements)
             │  measurements.json (shared batch format)
             ▼
        web/  Next.js /api/v1/ingest ─▶ supabase/ Postgres (RLS) ─▶ Next.js dashboard
             ▲
 wrist + gait teams upload the same batch format
```

| Folder | What |
|---|---|
| [`eye-tracking/`](eye-tracking/) | Python pipeline: camera, landmarks, stimulus protocol, calibration, events, features, export, upload, plots, synthetic benchmark, tests |
| [`supabase/`](supabase/) | SQL migrations (schema, RLS, ingest functions, raw-media storage policy) + synthetic seed |
| [`web/`](web/) | Next.js 15 API routes + minimal dashboard + DB/API tests (PGlite) |
| [`docs/`](docs/) | [Research & decision](docs/RESEARCH.md) · [Eye tracking](docs/EYE_TRACKING.md) · [Backend](docs/BACKEND.md) · [Data format for teammates](docs/DATA_FORMAT.md) |

## Status
**Implemented and tested**
- Webcam pipeline with a stimulus protocol (calibration, fixation, prosaccades, pursuit) → 21 measurements with confidence and quality flags → JSON/CSV/plot.
- Synthetic ground-truth benchmark showing what each camera frame rate can measure.
- Supabase schema for studies, participants, sessions, multi-device recordings, measurements, events, predictions and reports, with RLS, consent-gated raw media and device-key ingest.
- Next.js API (sessions, ingest, summaries, history, export, predictions) and dashboard pages.
- Tests: Python 18 passed; web 21 passed (migrations + RLS + real route handlers against real SQL in PGlite); `next build` and `tsc` clean.

**Not yet done / not verified**
- Not yet run on a real face: the live `check-camera` / `record` commands need a person at the camera and have only been import-checked.
- Not yet run against a real Supabase instance (no Docker/Supabase CLI on the dev machine). The SQL is tested in PGlite, and the Supabase-specific pieces (auth, storage) are stubbed in tests.
- Pupil diameter (needs an IR camera), antisaccade task, rate limiting, CI.

## Quick start
```bash
# Eye tracking (Python 3.10–3.12; MediaPipe has no 3.13+ wheels pinned here)
cd eye-tracking
uv venv -p 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
bash scripts/download_model.sh
.venv/bin/python -m pytest -q
.venv/bin/eyetrack check-camera
.venv/bin/eyetrack record --out recordings/test01 --screen-width-cm 30 --distance-cm 50
```
```bash
# Backend (needs Docker + Supabase CLI for the live stack; tests don't)
cd web && npm install && npm test
```
Full backend setup: [docs/BACKEND.md](docs/BACKEND.md#run-locally). Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).

## Environment variables
| Where | Variable | Notes |
|---|---|---|
| `web/.env.local` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | public by design; RLS protects data. **No service-role key needed.** |
| `eye-tracking/.env` | `EYETRACK_API_URL`, `EYETRACK_DEVICE_KEY` | device key from `create_device()`; the seed has a local-only dev key |

## Licenses of what we build on
MediaPipe (Apache-2.0), OpenCV (Apache-2.0), NumPy/Matplotlib (BSD-style), Next.js (MIT),
supabase-js (MIT), zod (MIT). No GPL/AGPL dependency is used, so we keep the freedom to choose
our own license later. Phase-2 candidates Pupil Labs detectors (LGPL) and REMoDNaV (MIT) keep that freedom too.
