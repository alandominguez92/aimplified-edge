# Deploying AimplifiedEdge

The whole app ships as **one Docker image**: FastAPI serves both the API and the
built React frontend on a single origin (no CORS, no proxy). The image compiles
the C++ EV engine for Linux, bundles the trained ML models + Statcast table, and
runs the daily slate/grading job in-process.

## What's in the image

- **Frontend** built in a Node stage → served by FastAPI at `/`.
- **Backend** FastAPI (`uvicorn app.main:app`) with `/api/*`.
- **C++ engine** compiled from source with `g++` during the build.
- **ML models** (`backend/models/`) and **Statcast table**
  (`backend/data/statcast_whiff.csv`) copied in (bundled, not rebuilt).
- **Scheduler** — `RUN_SCHEDULER=1` runs `app.jobs.daily` every `SCHEDULER_HOURS`
  (default 3): logs picks + grades finished games. Replaces the Windows task.

## Environment variables

| Var | Purpose | Default (in Dockerfile) |
| --- | --- | --- |
| `SPORTSGAMEODDS_API_KEY` | **Set as a secret** — enables odds | (unset → no odds) |
| `DATA_DIR` | SQLite location (mount a volume here to persist) | `/data` |
| `RUN_SCHEDULER` | `1` to run the in-process daily job | `1` |
| `SCHEDULER_HOURS` | Hours between scheduler runs | `3` |
| `MLB_SEASON` | Season for stats | `2026` |
| `PORT` | Bound by uvicorn (most hosts set this) | `8000` |

## Test the container locally (needs Docker)

```bash
cd aimplified-edge
docker build -t aimplified-edge .
docker run -p 8000:8000 -e SPORTSGAMEODDS_API_KEY=your_key aimplified-edge
# open http://localhost:8000
```

## Option A — Fly.io (no GitHub needed; deploys the local Dockerfile)

```bash
# one-time: install flyctl and sign in (your account)
fly auth login
fly launch --no-deploy            # detects the Dockerfile; creates fly.toml
fly volumes create data --size 1  # persistent SQLite
# in fly.toml add a [mounts] entry: source="data" destination="/data"
fly secrets set SPORTSGAMEODDS_API_KEY=your_key
fly deploy
```

## Option B — Render (via GitHub + the included `render.yaml`)

1. Push this repo to GitHub (`git remote add origin … && git push -u origin main`).
2. Render dashboard → **New → Blueprint** → pick the repo (reads `render.yaml`).
3. Set the `SPORTSGAMEODDS_API_KEY` secret when prompted.
4. Deploy. (The persistent disk in `render.yaml` needs a paid instance; on the
   free tier, delete the `disk:` block — the track record then resets on redeploy.)

## Option C — Cloudflare Pages (frontend) + Fly (backend)

Puts the site on Cloudflare (free, always-on static hosting) with the Python/C++
backend on Fly. The frontend reaches the backend cross-origin via `VITE_API_BASE`
(CORS already allows `*.pages.dev`).

**1. Backend on Fly** — same as Option A. Note its URL, e.g. `https://aimplified-edge.fly.dev`.

**2. Frontend on Cloudflare Pages:**
```bash
cd aimplified-edge/frontend
npm i -g wrangler          # or use the Cloudflare dashboard
VITE_API_BASE="https://aimplified-edge.fly.dev" npm run build
wrangler pages deploy dist --project-name aimplified-edge
```
Or connect the repo in the Cloudflare dashboard with:
- **Root directory:** `aimplified-edge/frontend`
- **Build command:** `npm run build`
- **Output directory:** `dist`
- **Environment variable:** `VITE_API_BASE = https://aimplified-edge.fly.dev`

That's it — the Pages site is always-on even when your PC is off; it just needs
the Fly backend running (which is also always-on). `VITE_API_BASE` is baked in at
build time, so rebuild/redeploy Pages if the backend URL changes.

## Things to know

- **Your odds key is used by every visitor.** The app calls SportsGameOdds on
  each visitor's behalf; a public deploy draws down your free-tier budget.
- **No auth / rate-limiting.** This is a personal analytics app, not hardened for
  hostile traffic. Consider putting it behind the host's access controls if that
  matters.
- **Persistence.** Without a mounted volume at `DATA_DIR`, the SQLite DB (track
  record + line snapshots) is wiped on every redeploy/restart.
- **Cold model load.** First request after boot loads the ML models (a beat);
  subsequent requests are cached.
