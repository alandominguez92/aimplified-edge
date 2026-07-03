"""Batter-hits slate — a heuristic MVP parallel to the pitcher-strikeout board.

The slate comes from the odds feed (which batters have hit props), and the
projection is a transparent heuristic: expected hits/game from season-to-date
stats, with a binomial interval. Reuses the shared prop/EV/sharp machinery, so
the same UI renders it. (ML model + calibration + forward-logging are the
follow-up tier, mirroring how the strikeout board started.)
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta

import httpx

from ..schemas import PitcherProp, Projection, SharpSignal, Weather
from . import mlb_statsapi
from .slate import _build_books, _consensus_line, _sharp_signal, _slug
from .sportsgameodds import _initial_last, fetch_hits_slate, normalize_name

_HITS_TTL = 60.0
_STATS_TTL = 3600.0
# The hits board is curated to the hottest bats: rank the day's batters by their
# batting average over the trailing window and keep the top N. A minimum window
# AB floor keeps a 3-for-5 cameo from topping genuinely hot regulars.
_RECENT_DAYS = 10
_RECENT_MIN_AB = 15
_TOP_N = 20
_hits_cache: dict[str, tuple[float, list[PitcherProp]]] = {}
_stats_cache: dict[int, tuple[float, dict, dict]] = {}
_recent_cache: dict[str, tuple[float, dict, dict]] = {}


async def _hitting_stats(season: int) -> tuple[dict, dict]:
    """One bulk call -> {normalized_name: {g, ab, h}} + first-initial+last index."""
    hit = _stats_cache.get(season)
    if hit and time.time() - hit[0] < _STATS_TTL:
        return hit[1], hit[2]

    async with httpx.AsyncClient() as client:
        data = await mlb_statsapi._get(
            client, "/stats", stats="season", group="hitting", season=season,
            sportId=1, limit=2000, playerPool="All",
        )

    by_name: dict[str, dict] = {}
    by_il: dict[str, list[str]] = {}
    for s in data.get("stats", [{}])[0].get("splits", []):
        p = s.get("player") or {}
        st = s.get("stat") or {}
        name = normalize_name(p.get("fullName", ""))
        g = int(st.get("gamesPlayed", 0) or 0)
        if not name or g == 0:
            continue
        by_name[name] = {
            "g": g,
            "ab": int(st.get("atBats", 0) or 0),
            "h": int(st.get("hits", 0) or 0),
        }
        il = _initial_last(name)
        if il:
            by_il.setdefault(il, []).append(name)

    _stats_cache[season] = (time.time(), by_name, by_il)
    return by_name, by_il


async def _recent_form(date: str) -> tuple[dict, dict]:
    """Trailing-window hitting via one byDateRange call, for the 'hottest' ranking.

    Returns {normalized_name: {ab, h}} + first-initial+last index, same shape as
    _hitting_stats so _match() works on it unchanged.
    """
    hit = _recent_cache.get(date)
    if hit and time.time() - hit[0] < _STATS_TTL:
        return hit[1], hit[2]

    start = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=_RECENT_DAYS))
    async with httpx.AsyncClient() as client:
        data = await mlb_statsapi._get(
            client, "/stats", stats="byDateRange", group="hitting",
            sportId=1, startDate=start.strftime("%Y-%m-%d"), endDate=date,
            limit=2000, playerPool="All",
        )

    by_name: dict[str, dict] = {}
    by_il: dict[str, list[str]] = {}
    for s in data.get("stats", [{}])[0].get("splits", []):
        p = s.get("player") or {}
        st = s.get("stat") or {}
        name = normalize_name(p.get("fullName", ""))
        if not name:
            continue
        by_name[name] = {
            "ab": int(st.get("atBats", 0) or 0),
            "h": int(st.get("hits", 0) or 0),
        }
        il = _initial_last(name)
        if il:
            by_il.setdefault(il, []).append(name)

    _recent_cache[date] = (time.time(), by_name, by_il)
    return by_name, by_il


def _match(by_name: dict, by_il: dict, name: str) -> dict | None:
    if name in by_name:
        return by_name[name]
    il = _initial_last(name)
    if il:
        cands = by_il.get(il, [])
        if len(cands) == 1:
            return by_name[cands[0]]
    return None


def _project(stat: dict) -> tuple[float, float, float, float]:
    """Expected hits/game + a binomial ~90% interval + a confidence score."""
    g, ab, h = stat["g"], stat["ab"], stat["h"]
    proj = h / g
    exp_ab = ab / g if g else 4.0
    p = h / ab if ab else 0.25
    sd = max(0.45, math.sqrt(max(exp_ab * p * (1 - p), 0.05)))
    low = max(0.0, proj - 1.645 * sd)
    high = proj + 1.645 * sd
    confidence = min(0.85, 0.50 + min(g, 70) * 0.005)
    return proj, low, high, confidence


async def build_hits_slate(date: str, season: int) -> list[PitcherProp]:
    cached = _hits_cache.get(date)
    if cached and time.time() - cached[0] < _HITS_TTL:
        return cached[1]

    sgo = await fetch_hits_slate(date)
    by_name, by_il = await _hitting_stats(season)
    r_name, r_il = await _recent_form(date)

    # (recent_avg, prop) so we can keep only the hottest bats after the loop.
    scored: list[tuple[float, PitcherProp]] = []
    for name, info in sgo.items():
        if info.get("finished"):
            continue  # game's over — drop the batter from the board
        stat = _match(by_name, by_il, name)
        if stat is None:
            continue
        books = _build_books(info["books"])
        if not books:
            continue

        # "Hottest" = trailing-window batting average. Need a real sample of
        # recent at-bats to qualify, otherwise a small hot streak skews the list.
        recent = _match(r_name, r_il, name)
        if recent is None or recent["ab"] < _RECENT_MIN_AB:
            continue
        recent_avg = recent["h"] / recent["ab"]
        recent_line = f"{recent['h']}/{recent['ab']}"

        proj, low, high, conf = _project(stat)
        market_line = _consensus_line(books, fallback=round(proj * 2) / 2)
        edge = round(proj - market_line, 2)
        rec = "over" if edge >= 0.3 else "under" if edge <= -0.3 else None
        # Longshot alt lines (2.5+ hits) have near-certain unders at tiny payouts;
        # a big raw edge there isn't real value, so don't flag a recommendation.
        if market_line >= 2.5:
            rec = None

        prop_id = _slug(info["name"], info["team"], "h")
        sharp = _sharp_signal(prop_id, date, market_line, has_market=bool(books))

        projection = Projection(
            projected_k=round(proj, 1), low=round(low, 1), high=round(high, 1),
            confidence=round(conf, 2), edge=edge, recommended_side=rec,
            last5_k=[], park_factor=1.0,
            weather=Weather(temp_f=75, condition="clear"),
        )
        scored.append((
            recent_avg,
            PitcherProp(
                id=prop_id, market="hits",
                game_time=info["gameTime"] or f"{date}T00:00:00Z",
                pitcher=info["name"], team=info["team"], opponent=info["opponent"],
                is_home=info["isHome"], market_line=market_line, books=books,
                projection=projection, sharp=sharp,
                l10_avg=round(recent_avg, 3), l10_line=recent_line,
            ),
        ))

    # Keep only the top-N hottest bats, hottest first.
    scored.sort(key=lambda t: -t[0])
    props = [prop for _, prop in scored[:_TOP_N]]
    _hits_cache[date] = (time.time(), props)
    return props
