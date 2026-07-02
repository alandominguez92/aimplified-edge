"""Build a per-start training set from MLB StatsAPI game logs.

For each starting pitcher/season we walk their starts in date order and, for
each start, record features computed only from *prior* starts (season-to-date
rates, recent form) plus matchup context (opponent K rate, park, home/away).
The target is that start's strikeout total. Output is a CSV cached on disk so
training is a one-time fetch.

Run: python -m app.ml.dataset   (from the backend/ dir, with the venv active)
"""
from __future__ import annotations

import asyncio
import csv
from collections import deque
from pathlib import Path

import httpx

from ..services.mlb_statsapi import (
    PARK_FACTORS,
    _get,
    _parse_ip,
    fetch_team_abbrs,
    fetch_team_k_rate,
)
from . import statcast
from .features import FEATURES, TARGET

SEASONS = [2024, 2025]
TOP_STARTERS = 130          # per season, by games started
WARMUP_STARTS = 3           # skip until trailing stats are stable
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "training.csv"


async def _top_starter_ids(client: httpx.AsyncClient, season: int) -> list[int]:
    data = await _get(
        client, "/stats", stats="season", group="pitching", season=season,
        sportId=1, limit=TOP_STARTERS, sortStat="gamesStarted", playerPool="All",
    )
    splits = data.get("stats", [{}])[0].get("splits", [])
    return [s["player"]["id"] for s in splits if s.get("player")]


async def _game_log(client: httpx.AsyncClient, pid: int, season: int) -> list[dict]:
    data = await _get(
        client, f"/people/{pid}",
        hydrate=f"stats(group=[pitching],type=[gameLog],season={season})",
    )
    for block in data.get("people", [{}])[0].get("stats", []):
        if (block.get("type") or {}).get("displayName") == "gameLog":
            return block.get("splits", [])
    return []


def _rows_from_log(
    splits: list[dict], abbrs: dict[int, str], krates: dict[int, float],
    pid: int, season: int,
) -> list[dict]:
    """Turn one pitcher-season game log into training rows (starts only)."""
    rows: list[dict] = []
    cum_so = 0.0
    cum_ip = 0.0
    starts = 0
    last5: deque[int] = deque(maxlen=5)
    whiff_prev = statcast.prior_whiff(pid, season)  # skill prior, same all season

    # gameLog is chronological (oldest -> newest)
    for sp in splits:
        stat = sp.get("stat", {})
        if int(stat.get("gamesStarted", 0) or 0) != 1:
            continue  # relief outing, not a start

        so = int(stat.get("strikeOuts", 0) or 0)
        ip = _parse_ip(stat.get("inningsPitched"))

        # Emit a row using ONLY prior-start info, once trailing stats are stable.
        if starts >= WARMUP_STARTS and cum_ip > 0:
            opp_id = (sp.get("opponent") or {}).get("id")
            team_id = (sp.get("team") or {}).get("id")
            is_home = bool(sp.get("isHome"))
            home_id = team_id if is_home else opp_id
            park = PARK_FACTORS.get(abbrs.get(home_id, ""), 1.0)
            rows.append(
                {
                    "k9": round(cum_so * 9.0 / cum_ip, 3),
                    "ip_per_start": round(cum_ip / starts, 3),
                    "recent_k": round(sum(last5) / len(last5), 3),
                    "games_started": starts,
                    "opp_k_rate": round(krates.get(opp_id, 0.224), 4),
                    "park_factor": park,
                    "is_home": 1 if is_home else 0,
                    "whiff_prev": round(whiff_prev, 2),
                    "pitcher_id": pid,
                    "season": season,
                    TARGET: so,
                }
            )

        cum_so += so
        cum_ip += ip
        starts += 1
        last5.append(so)

    return rows


async def build_training_csv() -> Path:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(8)
    all_rows: list[dict] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for season in SEASONS:
            abbrs = await fetch_team_abbrs(client, season)
            # opponent season K rates, fetched once per team
            team_ids = list(abbrs.keys())
            krate_vals = await asyncio.gather(
                *(fetch_team_k_rate(client, tid, season) for tid in team_ids)
            )
            krates = dict(zip(team_ids, krate_vals))

            pids = await _top_starter_ids(client, season)

            async def one(pid: int, season=season, abbrs=abbrs, krates=krates) -> list[dict]:
                async with sem:
                    try:
                        log = await _game_log(client, pid, season)
                    except httpx.HTTPError:
                        return []
                return _rows_from_log(log, abbrs, krates, pid, season)

            results = await asyncio.gather(*(one(pid) for pid in pids))
            season_rows = [r for sub in results for r in sub]
            all_rows.extend(season_rows)
            print(f"  season {season}: {len(pids)} starters -> {len(season_rows)} start rows")

    cols = FEATURES + ["pitcher_id", "season", TARGET]
    with OUT_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(all_rows)

    print(f"wrote {len(all_rows)} rows -> {OUT_PATH}")
    return OUT_PATH


if __name__ == "__main__":
    asyncio.run(build_training_csv())
