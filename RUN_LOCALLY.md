# Run everything locally: copy-paste guide (macOS)

The project lives in `~/Documents/Projects/pd-eye-tracking`.
You need **two Terminal windows**: one keeps the website running, the other runs everything else.

---
## Part A: Eye tracking (works right now, no accounts needed)

```bash
cd ~/Documents/Projects/pd-eye-tracking/eye-tracking
```
First time only (the Python environment is already built on this Mac; these commands just refresh it):
```bash
~/.local/bin/uv venv -p 3.12 .venv && ~/.local/bin/uv pip install --python .venv/bin/python -e ".[dev]"
```
```bash
bash scripts/download_model.sh
```
Check that everything works:
```bash
.venv/bin/python -m pytest -q
```
Expected: `18 passed`.

Camera check (10 s). macOS will ask to allow camera access for Terminal; click **Allow**, then run it again:
```bash
.venv/bin/eyetrack check-camera
```
Full recording, about 100 s. Replace `30` with your screen's visible width in cm. Press SPACE when you see "face OK", then follow the dot with your eyes only:
```bash
.venv/bin/eyetrack record --out recordings/self01 --screen-width-cm 30 --distance-cm 50
```
Open the plot:
```bash
open recordings/self01/plot.png
```

---
## Part B: Backend + dashboard (needs Docker Desktop, one-time install)

1. Download and install **Docker Desktop for Mac (Apple silicon)** from https://www.docker.com/products/docker-desktop/ , open it, and wait until it says "Engine running".

2. Start the local Supabase database (the first run downloads about 1–2 GB; press Enter at any questions):
```bash
cd ~/Documents/Projects/pd-eye-tracking
```
```bash
npx supabase init
```
```bash
npx supabase start
```
```bash
npx supabase db reset
```

3. Give the website the database address and public key:
```bash
npx supabase status -o env | grep -E '^(API_URL|ANON_KEY)=' | sed -e 's/^API_URL=/NEXT_PUBLIC_SUPABASE_URL=/' -e 's/^ANON_KEY=/NEXT_PUBLIC_SUPABASE_ANON_KEY=/' | tr -d '"' > web/.env.local && cat web/.env.local
```
You should see two lines, both with values. If either is empty, run `npx supabase status` and copy the "API URL" and "anon key" into `web/.env.local` by hand.

4. **Terminal window 1**: start the website (leave it running):
```bash
cd ~/Documents/Projects/pd-eye-tracking/web && npm install && npm run dev
```

5. **Terminal window 2**: send eye data into the system:
```bash
cd ~/Documents/Projects/pd-eye-tracking/eye-tracking
```
```bash
export EYETRACK_API_URL=http://localhost:3000 EYETRACK_DEVICE_KEY=dk_local_dev_eye_key_do_not_use_in_production
```
Synthetic data first (proves the pipeline end to end):
```bash
.venv/bin/eyetrack simulate --out recordings/syn01 --fps 30 && .venv/bin/eyetrack upload recordings/syn01 --participant SYN-101
```
Then your own recording from Part A:
```bash
.venv/bin/eyetrack upload recordings/self01 --participant SYN-101
```

6. Open http://localhost:3000 and sign in with `dev@example.test` / `devpassword123`.
   Your sessions, measurements, quality flags and a CSV download link are there.

Stop everything when you're done: `Ctrl+C` in window 1, then `npx supabase stop` in the project folder.

---
## If something goes wrong
| Symptom | Fix |
|---|---|
| `Could not open camera 0` | System Settings → Privacy & Security → Camera → turn on Terminal, then quit and reopen Terminal |
| `Cannot connect to the Docker daemon` | Open Docker Desktop and wait for "Engine running" |
| `Upload failed (401)` | The `export EYETRACK_…` line wasn't run in this window, or `db reset` wasn't run |
| `Upload failed (404) unknown participant` | Use one of the seeded codes: `SYN-001`, `SYN-002`, `SYN-003`, `SYN-101` |
| Website shows "fetch failed" on login | `web/.env.local` is wrong or Supabase isn't running (`npx supabase status`) |
