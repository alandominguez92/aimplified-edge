"""AimplifiedEdge API — FastAPI entry point.

Routes are mounted under /api to match the Vite dev proxy. The frontend talks
only to this origin; this service fans out to MLB StatsAPI and SportsGameOdds.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import date as date_cls, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import db
from .config import get_settings
from .engine import cpp_kelly, ml_projection
from .jobs.daily import main as daily_job
from .schemas import ParlayLeg, PitcherProp
from .services import results
from .services.hits import build_hits_slate, hits_odds_as_of
from .services.slate import build_slate, slate_odds_as_of


def _set_odds_freshness(response: Response, as_of: float | None) -> None:
    """Tell the client whether the odds are a stale fallback (and from when)."""
    if as_of is not None:
        response.headers["X-Odds-As-Of"] = (
            datetime.fromtimestamp(as_of, tz=timezone.utc).isoformat()
        )

settings = get_settings()


def _today() -> str:
    return date_cls.today().isoformat()


async def _scheduler() -> None:
    """In-process daily job for hosted deploys (replaces the Windows task).

    Enabled with RUN_SCHEDULER=1; interval via SCHEDULER_HOURS (default 12).
    12h = ~2 runs/day, which keeps the SportsGameOdds free-tier object budget
    in check while still capturing an open + closing line snapshot per pick."""
    interval = int(os.getenv("SCHEDULER_HOURS", "12")) * 3600
    # Let uvicorn bind + pass Fly's health check before the first (heavy) run.
    await asyncio.sleep(30)
    while True:
        try:
            await daily_job()
        except Exception:
            pass
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    try:
        await results.grade_open_picks(_today())
    except Exception:  # never block startup on grading
        pass

    task = None
    if os.getenv("RUN_SCHEDULER") == "1":
        task = asyncio.create_task(_scheduler())
    yield
    if task:
        task.cancel()


app = FastAPI(title="AimplifiedEdge API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    # Split deploy: allow the Cloudflare Pages site (prod + preview subdomains).
    allow_origin_regex=r"https://.*\.pages\.dev",
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Odds-As-Of"],  # let the browser read the stale-odds flag
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "oddsEnabled": settings.odds_enabled,
        "projectionModel": "ml" if ml_projection.available() else "heuristic",
        "evEngine": "cpp" if cpp_kelly.available() else "python",
    }


@app.get("/api/model")
def model_info() -> dict:
    """Projection model status + held-out evaluation metrics."""
    return {
        "active": "ml" if ml_projection.available() else "heuristic",
        "metrics": ml_projection.metrics(),
        "calibration": ml_projection.calibration(),
    }


@app.get("/api/sports")
def sports() -> list[dict]:
    return [
        {"id": "MLB", "live": True},
        {"id": "NBA", "live": False},
        {"id": "NHL", "live": False},
        {"id": "NFL", "live": False},
        {"id": "Soccer", "live": False},
    ]


@app.get("/api/mlb/props", response_model=list[PitcherProp])
async def mlb_props(
    response: Response,
    date: str = Query(default_factory=lambda: date_cls.today().isoformat()),
) -> list[PitcherProp]:
    props = await build_slate(date, settings.mlb_season)
    _set_odds_freshness(response, slate_odds_as_of(date))
    return props


@app.get("/api/mlb/hits", response_model=list[PitcherProp])
async def mlb_hits(
    response: Response,
    date: str = Query(default_factory=lambda: date_cls.today().isoformat()),
) -> list[PitcherProp]:
    props = await build_hits_slate(date, settings.mlb_season)
    _set_odds_freshness(response, hits_odds_as_of(date))
    return props


@app.get("/api/mlb/props/{prop_id}", response_model=PitcherProp)
async def mlb_prop(
    prop_id: str,
    date: str = Query(default_factory=lambda: date_cls.today().isoformat()),
) -> PitcherProp:
    for p in await build_slate(date, settings.mlb_season):
        if p.id == prop_id:
            return p
    raise HTTPException(status_code=404, detail="prop not found")


@app.get("/api/picks/record")
async def picks_record() -> dict:
    """Forward track record. Grades any newly-finished games first, then sums."""
    await results.grade_open_picks(_today())
    return results.record_summary()


@app.get("/api/picks")
def picks_list(limit: int = 100) -> list[dict]:
    return [dict(r) for r in db.all_picks(limit)]


@app.get("/api/picks/history")
async def picks_history() -> list[dict]:
    """Graded picks with running cumulative units (grades finished games first)."""
    await results.grade_open_picks(_today())
    return results.history()


@app.post("/api/parlay")
def parlay(legs: list[ParlayLeg]) -> dict:
    """Combined parlay EV via the C++ engine: naive (independence) vs a
    Monte-Carlo same-game correlation adjustment."""
    return cpp_kelly.parlay([(leg.prob, leg.odds, leg.game_key) for leg in legs])


# Serve the built frontend from this same service (single origin, no CORS/proxy).
# Mounted last so /api/* routes take precedence. Skipped in local dev (use Vite).
# The app is a single page, so StaticFiles(html=True) covers all routing.
_DIST = Path(
    os.getenv("FRONTEND_DIST", str(Path(__file__).resolve().parents[2] / "frontend" / "dist"))
)
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
