# AimplifiedEdge

MLB / multi-sport **pitcher-prop & line-analysis dashboard** — a dark
"trading terminal" UI that pairs model strikeout projections with live
multi-sportsbook lines, EV/Kelly sizing, and a sharp-money signal layer.

> ⚠️ For analytical / entertainment use. Projections, EV, and sharp signals are
> illustrative and not betting advice.

## Status

This is an in-progress build.

**Milestone 1 — frontend UI shell — done.**
- Dark sportsbook theme (`#0A0E1A` base, `#00FFB2` mint, `#FF4C4C` risk),
  JetBrains Mono for all numbers.
- Sortable pitcher-prop table (game time, projection edge, line value, sharp
  signal) with FanDuel / DraftKings / Underdog / BetMGM columns, color-coded
  odds cells, and a hover mini stat card (last-5 K, park factor, weather).
- Right-rail **Prediction card**: projected K, confidence interval, EV%, Kelly
  tier + unit size, and a pulsing sharp-money indicator.
- **Parlay slip**: click odds to add legs, with same-game correlation warnings
  and combined EV / max-exposure.

**Milestone 2 — FastAPI backend + live data pipeline — done.**
- **MLB StatsAPI** (free, no key): probable pitchers + game times, each
  starter's season K-rate, opponent strikeout tendency, and last-5-start K logs.
- **ML projection engine** (`app/ml/`, `app/engine/ml_projection.py`): three
  gradient-boosted quantile models (5th/50th/95th, scikit-learn
  `HistGradientBoostingRegressor`) trained on ~6.2k starts from 2024–25 MLB
  StatsAPI game logs. Features (leakage-safe, computed from prior starts):
  season K/9, IP/start, last-5 K, starts-to-date, opponent K-rate, park, home,
  and **prior-season whiff%** (Statcast, via `app/ml/statcast.py` / Baseball
  Savant). Honest note on whiff%: it's a real signal (permutation-importance #3),
  but largely *redundant with K/9*, so it barely moves MAE — per-start K is
  noise-dominated. It's wired as the hook for richer Statcast features.
  The 90% interval is **conformalized (CQR)** to hit real coverage. Falls back to
  the heuristic (`app/engine/projection.py`) if model artifacts are missing.
  Status + held-out metrics at `GET /api/model`.
- **Backtest + calibration** (`app/ml/backtest.py`): grades the model on the
  held-out test split and learns two corrections applied at serve time — a
  **projection de-bias** (the raw model over-spreads at the tails; a linear map
  pulls extremes back toward reality) and a **probability scale** (checks that
  "68% over" hits ~68%; it does — ECE ≈ 0.02, so the EV/Kelly inputs are sound).
  The de-bias matters: it removes inflated extreme "edges" that were projection
  artifacts, so the app's recommendations are conservative and trustworthy
  rather than eye-catching. Corrections live in `models/calibration.json`.
- **C++ EV/Kelly engine** (`backend/engine/*.cpp`, wrapper `app/engine/cpp_kelly.py`):
  implied-prob / EV / Kelly / decimal↔American, mirroring `odds_math.py` — verified
  equal to the Python oracle to ~5e-10 across 2k cases. Called as a subprocess
  binary (whitespace protocol) with a transparent Python fallback. Its real job
  is a **Monte-Carlo same-game parlay correlation** model (single-factor Gaussian
  copula): independence understates a same-game parlay's true win %, and the MC
  computes the correlation-adjusted probability — **~15× faster than Python**
  (300k sims: 0.017s vs 0.25s). Exposed at `POST /api/parlay`; the parlay slip
  shows the "correlation-adjusted (C++ MC)" line. Honest note: for the *trivial*
  EV/Kelly math the subprocess overhead makes Python faster, so the app serves
  those in Python — C++ earns its place only on the heavy MC path.
- **Forward track record** (`app/services/results.py`, `app/db.py` picks table):
  every actionable recommendation is logged when first flagged (side, best
  price/book, projection, edge, EV) and **graded once the game is final** —
  actual strikeouts from StatsAPI game logs → win/loss/push, flat-1u profit, and
  **CLV** (line-at-pick vs closing line from the snapshot table). Real bet ROI
  needs odds-at-bet-time and outcomes, which can't be backfilled (SGO free is
  current-day), so this accrues going forward rather than faking a backtest. The
  right-rail **Track record** card surfaces record / ROI / hit-rate / CLV, and a
  **Performance** chart (SVG cumulative-units line, no chart lib) appears below
  the table once picks start grading.
- **EV/Kelly engine** (`app/engine/odds_math.py`): Python port of the frontend
  `lib/odds.ts`, kept line-for-line in sync (and the oracle for the C++ port).
- **SportsGameOdds** (`app/services/sportsgameodds.py`): MLB `pitching_strikeouts`
  props from `/v2/events`, gated on `SPORTSGAMEODDS_API_KEY` (free tier).
  Matches props to starters by player name (decoded from `statEntityID`): exact
  normalized full name, then an unambiguous first-initial + last-name fallback
  (so "Matt" ↔ "Matthew" matches, while Eury vs Martín Pérez stay distinct).
  Free-tier books seen: FanDuel, DraftKings, Caesars, ESPN BET, Bovada — the
  table shows the first four; the prediction card shops the best price across
  all of them. Without a key the slate still renders from StatsAPI +
  projections; book columns are empty and there's no market line to find edges
  against (so value highlights/EV need a key).
- **Sharp-money layer**: open→current line movement tracked in SQLite
  (`app/db.py`). Ticket % isn't in our current sources, so it's a neutral
  placeholder until a tickets feed is added.
- The frontend reads `/api/mlb/props` via `data/slate.ts` and falls back to the
  bundled mock if the API is down (a `LIVE`/`MOCK` badge shows which).
- **Auto-refresh:** the UI polls every 60s (pausing when the tab is hidden,
  refreshing on focus) with an "updated Xs ago" indicator + manual refresh. To
  stay within the free-tier budget the backend (a) fetches only the
  `pitching_strikeouts` market via the `oddIDs=…-PLAYER_ID-…` filter (~30 odds
  objects/slate instead of ~9k) and (b) caches the assembled slate ~60s and the
  StatsAPI probable-pitchers/stats ~10min. Each rebuild records a line snapshot,
  so the sharp-money signal accrues real open→current movement through the day.

## Run it

Two terminals.

**Backend** (port 8000):
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
cp .env.example .env            # add SPORTSGAMEODDS_API_KEY to enable book odds
python -m app.ml.statcast       # optional: pull whiff% from Baseball Savant
python -m app.ml.dataset        # optional: build training set from StatsAPI (~2 min)
python -m app.ml.train          # optional: train projection models -> models/
python -m app.ml.backtest       # optional: grade + calibrate (writes calibration.json)
uvicorn app.main:app --reload --port 8000
```

The ML steps are optional — without `models/` the API serves the heuristic
projection and `GET /api/model` reports `"active": "heuristic"`. Run them in
order (`statcast → dataset → train → backtest`): `statcast` builds the whiff
table the dataset joins, `train` fits the models, `backtest` learns the
projection de-bias + probability calibration on held-out data.

The C++ EV engine is also optional (Python fallback if absent). Build it with a
self-contained g++ (e.g. `winget install BrechtSanders.WinLibs.POSIX.UCRT`):

```powershell
backend\engine\build.ps1        # compiles kelly_engine.exe, runs selftest
```
`GET /api/health` reports `"evEngine": "cpp"` when the binary is present.

**Frontend** (port 5174, proxies `/api` → backend):
```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5174.

## Deploy

The app ships as **one Docker image** — FastAPI serves the API and the built
frontend on a single origin, with the C++ engine compiled for Linux and the ML
models bundled. See **[DEPLOY.md](DEPLOY.md)** for Fly.io / Render steps. Quick
local container check:

```bash
docker build -t aimplified-edge .
docker run -p 8000:8000 -e SPORTSGAMEODDS_API_KEY=your_key aimplified-edge  # http://localhost:8000
```

## Daily automation (track record accrues unattended)

`app/jobs/daily.py` builds today's slate (logging new picks + a line snapshot)
and grades finished games. Run it manually, or on a schedule so the track record
fills in without opening the app:

```bash
python -m app.jobs.daily        # one run; appends to backend/jobs.log
```

A Windows scheduled task registered as **`AimplifiedEdge-Daily`** runs it at
10:00/13:00/16:00/19:00/22:00 daily (via `pythonw`, no console window). Manage it:

```powershell
Start-ScheduledTask   -TaskName AimplifiedEdge-Daily   # run now
Get-ScheduledTaskInfo -TaskName AimplifiedEdge-Daily   # last/next run
Unregister-ScheduledTask -TaskName AimplifiedEdge-Daily -Confirm:$false  # remove
```

(macOS/Linux equivalent: a cron entry calling the same `python -m app.jobs.daily`.)

## API endpoints
| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/health` | Health + odds enabled + projection model (ml/heuristic) |
| GET | `/api/sports` | Supported sports |
| GET | `/api/model` | Projection model status + held-out metrics |
| GET | `/api/mlb/props?date=YYYY-MM-DD` | Today's pitcher-strikeout slate (default: today) |
| GET | `/api/mlb/hits?date=YYYY-MM-DD` | Today's batter-hits slate (heuristic projections) |
| GET | `/api/mlb/props/{id}` | A single pitcher prop |
| GET | `/api/picks/record` | Forward track record (grades finished games, then sums) |
| GET | `/api/picks/history` | Graded picks with running cumulative units |
| GET | `/api/picks` | Logged picks (most recent first) |
| POST | `/api/parlay` | Combined parlay EV via the C++ engine (naive + correlation-adjusted) |

## Roadmap (remaining)

1. **Statcast features** — add SwStr%, CSW%, pitch mix (via pybaseball/Baseball
   Savant) to the training set. With box-score-only features the model sits near
   the per-start noise floor (~1.82 MAE, barely past the season-rate heuristic);
   the plate-discipline signals are the expected accuracy unlock.
2. **Richer Statcast features** — prior-season whiff% is in (marginal: redundant
   with K/9). The likelier unlock is *in-season trailing* CSW%/whiff and pitch
   mix from pitch-level Savant data (`statcast_pitcher`), heavier to pull.
3. **C++ engine follow-ups** — a pybind11 module (drop the subprocess I/O
   overhead) and per-leg correlation coefficients instead of one global ρ.
4. **Richer sharp layer** — real ticket %/handle feed.
5. **Stretch** — track-record history/charts tab, PDF/graphic export, WebSocket
   live odds.

## Layout

```
aimplified-edge/
├── backend/             # FastAPI + httpx + scikit-learn + C++ engine
│   ├── engine/          # kelly.h/.cpp + main.cpp -> kelly_engine.exe (build.ps1)
│   └── app/
│       ├── main.py          # routes (/api/...)
│       ├── schemas.py       # Pydantic models == frontend types (camelCase)
│       ├── db.py            # SQLite line snapshots + picks
│       ├── engine/          # odds_math, projection, ml_projection, cpp_kelly (C++ wrapper)
│       ├── ml/              # features, statcast (whiff), dataset, train (quantile+CQR), backtest
│       ├── jobs/            # daily.py — scheduled slate-build + grading
│       └── services/        # mlb_statsapi, sportsgameodds, slate, results (track record)
├── frontend/            # React 19 + Vite + Tailwind v4 (Milestone 1)
│   └── src/
│       ├── components/  # TopNav, PropTable, PredictionCard, ParlaySlip, ...
│       ├── lib/         # odds (EV/Kelly), projection (prob), format
│       ├── data/        # slate.ts — live fetch + mock fallback
│       └── types.ts
└── README.md
```
