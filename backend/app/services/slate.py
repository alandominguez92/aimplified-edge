"""Assemble the pitcher-prop slate the frontend consumes.

Combines: StatsAPI probable pitchers + season/opponent stats (projection),
SportsGameOdds strikeout props (book lines), and SQLite line-movement snapshots
(sharp signal) into `schemas.PitcherProp` objects.
"""
from __future__ import annotations

import re
import time
from collections import Counter

from .. import db
from ..engine import ml_projection, odds_math
from ..engine.projection import project, prob_for_side
from ..ml import statcast
from ..schemas import (
    BookOdds,
    BookSide,
    PitcherProp,
    Projection,
    SharpSignal,
    Weather,
)
from . import mlb_statsapi, results
from .sportsgameodds import fetch_strikeout_props, match_books

BOOK_ORDER = ["FanDuel", "DraftKings", "Caesars", "ESPN BET", "BetMGM", "Bovada"]

# Caches: probable pitchers + season stats change slowly (10 min); the assembled
# slate is cached briefly (60s) so frequent polling doesn't re-hit SportsGameOdds
# (protecting the free-tier budget) and so line snapshots accrue at ~60s cadence.
_RAW_TTL = 600.0
# Assembled-slate cache. This is the real SportsGameOdds budget guard: the SGO
# feed is only re-fetched when this expires, no matter how often clients poll.
# 5 min keeps the free tier comfortable while lines stay reasonably fresh.
_SLATE_TTL = 300.0
_raw_cache: dict[tuple[str, int], tuple[float, list[dict]]] = {}
# (fetch_ts, props, odds_as_of). odds_as_of is None when the slate carries fresh
# odds, else the epoch time the reused (stale) odds were last fetched live.
_slate_cache: dict[str, tuple[float, list["PitcherProp"], float | None]] = {}
# Last odds response that actually had book lines, per date. When SportsGameOdds
# fails (429/free-tier cap), we rebuild the slate fresh from StatsAPI but feed
# these stale odds back in, so the board shows last-known lines instead of blank.
_last_odds: dict[str, tuple[float, dict]] = {}


def _slug(*parts: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", "-".join(parts).lower()).strip("-")


def _consensus_line(books: list[BookOdds], fallback: float) -> float:
    points = [
        side.line
        for b in books
        for side in (b.over, b.under)
        if side is not None
    ]
    if not points:
        return fallback
    # most common line, ties broken toward the lower (more common .5 line)
    return Counter(points).most_common(1)[0][0]


def _build_books(odds_for_pitcher: dict) -> list[BookOdds]:
    books: list[BookOdds] = []
    for name in BOOK_ORDER:
        entry = odds_for_pitcher.get(name)
        if not entry:
            continue
        books.append(
            BookOdds(
                book=name,
                over=BookSide(**entry["over"]) if entry.get("over") else None,
                under=BookSide(**entry["under"]) if entry.get("under") else None,
            )
        )
    return books


def _sharp_signal(prop_key: str, day: str, line: float, has_market: bool) -> SharpSignal:
    """Best-effort: derived purely from open->current line movement we've stored.

    Only *real* market lines are tracked — when there are no book odds we skip
    recording so a projection-derived placeholder line can't pollute the
    movement history and trip a false signal. Ticket % isn't available from our
    current sources, so it's reported as 50 (neutral) until a tickets feed is
    added. With no prior snapshots the signal is silent (side=None)."""
    if not has_market:
        return SharpSignal(side=None, strength=0.0, ticket_pct=50,
                           open_line=line, current_line=line)
    db.record_line(prop_key, day, line)
    open_line, current = db.open_and_current(prop_key, day)
    if open_line is None or current is None:
        return SharpSignal(side=None, strength=0.0, ticket_pct=50,
                           open_line=line, current_line=line)
    delta = current - open_line
    strength = min(0.95, abs(delta) * 1.4)
    side = None
    if strength > 0.6:
        side = "over" if delta > 0 else "under"
    return SharpSignal(
        side=side, strength=round(strength, 2), ticket_pct=50,
        open_line=open_line, current_line=current,
    )


def _project(r: dict, season: int) -> dict:
    """ML projection when models are trained, else the heuristic fallback."""
    stats = r["stats"]
    if ml_projection.available():
        recent_k = (
            sum(r["last5_k"]) / len(r["last5_k"])
            if r["last5_k"]
            else stats.k9 / 9.0 * stats.innings_per_start
        )
        return ml_projection.project(
            k9=stats.k9,
            ip_per_start=stats.innings_per_start,
            recent_k=recent_k,
            games_started=stats.games_started,
            opp_k_rate=r["opp_k_rate"],
            park_factor=r["park_factor"],
            is_home=r["is_home"],
            whiff_prev=statcast.prior_whiff(r["pid"], season),
        )
    return project(stats, r["opp_k_rate"], r["park_factor"])


async def _get_raw(date: str, season: int) -> list[dict]:
    key = (date, season)
    hit = _raw_cache.get(key)
    if hit and time.time() - hit[0] < _RAW_TTL:
        return hit[1]
    raw = await mlb_statsapi.fetch_raw_slate(date, season)
    _raw_cache[key] = (time.time(), raw)
    return raw


def slate_odds_as_of(date: str) -> float | None:
    """Epoch time of the odds in the last-built slate, or None if they're fresh.

    Endpoints read this to flag a stale-odds fallback in the response.
    """
    entry = _slate_cache.get(date)
    return entry[2] if entry else None


async def build_slate(date: str, season: int) -> list[PitcherProp]:
    hit = _slate_cache.get(date)
    if hit and time.time() - hit[0] < _SLATE_TTL:
        return hit[1]

    raw = await _get_raw(date, season)
    odds = await fetch_strikeout_props(date)

    # Odds resilience: remember the last response that had lines; if this fetch
    # came back empty (SGO down / rate-limited), reuse the last-known odds and
    # mark the slate stale so projections stay fresh but lines don't vanish.
    odds_as_of: float | None = None
    if odds:
        _last_odds[date] = (time.time(), odds)
    elif date in _last_odds:
        odds_as_of, odds = _last_odds[date]

    props: list[PitcherProp] = []
    pitcher_ids: dict[str, int] = {}
    for r in raw:
        proj_raw = _project(r, season)

        books = _build_books(match_books(odds, r["pitcher"]))
        derived = round(proj_raw["projected_k"] * 2) / 2
        market_line = _consensus_line(books, fallback=derived)

        edge = round(proj_raw["projected_k"] - market_line, 1)
        rec = "over" if edge >= 0.75 else "under" if edge <= -0.75 else None

        prop_id = _slug(r["pitcher"], r["team"])
        pitcher_ids[prop_id] = r["pid"]
        sharp = _sharp_signal(prop_id, date, market_line, has_market=bool(books))

        projection = Projection(
            projected_k=proj_raw["projected_k"],
            low=proj_raw["low"],
            high=proj_raw["high"],
            confidence=proj_raw["confidence"],
            edge=edge,
            recommended_side=rec,
            last5_k=r["last5_k"],
            park_factor=r["park_factor"],
            weather=Weather(
                temp_f=72 if r["is_dome"] else 75,
                condition="dome" if r["is_dome"] else "clear",
            ),
        )

        props.append(
            PitcherProp(
                id=prop_id,
                game_time=r["game_time"],
                pitcher=r["pitcher"],
                team=r["team"],
                opponent=r["opponent"],
                is_home=r["is_home"],
                market_line=market_line,
                books=books,
                projection=projection,
                sharp=sharp,
            )
        )

    results.log_picks(date, props, pitcher_ids)
    _slate_cache[date] = (time.time(), props, odds_as_of)
    return props


# Re-export for the EV math used by any future /ev endpoint or tests.
__all__ = ["build_slate", "odds_math", "prob_for_side"]
