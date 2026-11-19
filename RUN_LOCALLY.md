# Run everything locally: copy-paste guide (macOS)

The project can live in any folder. Every command below uses paths **relative to the project folder** (the one that contains this file, `requirements.txt`, `eye-tracking/` and `web/`).

To open Terminal in the project folder: type `cd ` (with a space), drag the project folder from Finder onto the Terminal window, then press Enter. Do this in **every new Terminal window**.

You need **two Terminal windows**: one keeps the website running, the other runs everything else.

---
## Part A: Eye tracking (no accounts needed)

### First time only: install Python and the dependencies

1. Install `uv` (a fast Python installer that also downloads the right Python version). Skip this if `uv --version` already works:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Then close and reopen Terminal, and `cd` into the project folder again.

2. Create the Python environment and install everything from `requirements.txt` (Python 3.12 is required; MediaPipe does not support 3.13 yet). This includes PyTorch for the neural pupil detector, about 700 MB:
```bash
uv venv -p 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
```
Without `uv`, the same thing with a Python 3.12 you already have:
```bash
python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
```

3. Download the face model (about 4 MB, checksum verified):
```bash
bash eye-tracking/scripts/download_model.sh
```

### Every new Terminal window

Activate the environment so `eyetrack` and `python` point at it:
```bash
source .venv/bin/activate
```

### Check that everything works
```bash
(cd eye-tracking && python -m pytest -q) && (cd ml && python -m pytest -q)
```
Expected: `38 passed`, then `8 passed`.

### Record yourself

Run these from the `eye-tracking` folder so recordings land in `eye-tracking/recordings/` (git ignores that folder):
```bash
cd eye-tracking
```
Camera check (10 s). macOS will ask to allow camera access for Terminal; click **Allow**, then run it again:
```bash
eyetrack check-camera
```
Full recording, about 100 s. Replace `30` with your screen's visible width in cm. Press SPACE when you see "face OK", then follow the dot with your eyes only:
```bash
eyetrack record --out recordings/self01 --screen-width-cm 30 --distance-cm 50
```
Open the plot:
```bash
open recordings/self01/plot.png
```
Go back to the project folder when you're done:
```bash
cd ..
```

---
## Part B: Backend + dashboard (needs Docker Desktop and Node.js)

1. Install **Docker Desktop for Mac** from https://www.docker.com/products/docker-desktop/ , open it, and wait until it says "Engine running". Install **Node.js** (LTS) from https://nodejs.org/ if `node -v` doesn't work.

2. Start the local Supabase database from the project folder (the first run downloads about 1–2 GB):
```bash
npx supabase start
```
Create the tables and load the synthetic test data (wipes the local database):
```bash
npx supabase db reset
```

3. Give the website the database address and public key:
```bash
npx supabase status -o env | grep -E '^(API_URL|ANON_KEY)=' | sed -e 's/^API_URL=/NEXT_PUBLIC_SUPABASE_URL=/' -e 's/^ANON_KEY=/NEXT_PUBLIC_SUPABASE_ANON_KEY=/' | tr -d '"' > web/.env.local && cat web/.env.local
```
You should see two lines, both with values. If either is empty, run `npx supabase status` and copy the "API URL" and "anon key" into `web/.env.local` by hand.

4. **Terminal window 1**: start the website from the project folder (leave it running):
```bash
cd web && npm install && npm run dev
```

5. **Terminal window 2**: open a new window, `cd` into the project folder, then send eye data into the system:
```bash
source .venv/bin/activate && cd eye-tracking
```
```bash
export EYETRACK_API_URL=http://localhost:3000 EYETRACK_DEVICE_KEY=dk_local_dev_eye_key_do_not_use_in_production
```
Synthetic data first (proves the pipeline end to end):
```bash
eyetrack simulate --out recordings/syn01 --fps 30 && eyetrack upload recordings/syn01 --participant SYN-101
```
Then your own recording from Part A:
```bash
eyetrack upload recordings/self01 --participant SYN-101
```

6. Open http://localhost:3000 and sign in with `dev@example.test` / `devpassword123`.
   Your sessions, measurements, quality flags and a CSV download link are there.

Stop everything when you're done: `Ctrl+C` in window 1, then `npx supabase stop` in the project folder.

---
## If something goes wrong
| Symptom | Fix |
|---|---|
| `eyetrack: command not found` | Run `source .venv/bin/activate` from the project folder in this window |
| `No such file or directory: requirements.txt` | You're not in the project folder; `cd` into it first |
| `bad interpreter` from `.venv/bin/pip` | The project folder was moved or renamed after `.venv` was made. Delete `.venv` and redo Part A step 2 |
| `Could not open camera 0` | System Settings → Privacy & Security → Camera → turn on Terminal, then quit and reopen Terminal |
| `Cannot connect to the Docker daemon` | Open Docker Desktop and wait for "Engine running" |
| `Upload failed (401)` | The `export EYETRACK_…` line wasn't run in this window, or `db reset` wasn't run |
| `Upload failed (404) unknown participant` | Use one of the seeded codes: `SYN-001`, `SYN-002`, `SYN-003`, `SYN-101` |
| Website shows "fetch failed" on login | `web/.env.local` is wrong or Supabase isn't running (`npx supabase status`) |
