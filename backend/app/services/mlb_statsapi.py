"""MLB StatsAPI integration (free, no key) — statsapi.mlb.com.

Pulls the day's probable pitchers + game times from the schedule, then each
starter's season strikeout rate and the opposing lineup's strikeout tendency.
These feed the projection engine.
"""
from __future__ import annotations

import asyncio

import httpx

from ..engine.projection import LEAGUE_K_RATE, PitcherStats

BASE = "https://statsapi.mlb.com/api/v1"

# Rough hitter-friendly/pitcher K park factors and domed venues (by home abbr).
# A real build would pull these from a park-factors source; this keeps the
# adjustment honest-ish without another live dependency.
PARK_FACTORS: dict[str, float] = {
    "COL": 0.93, "BOS": 1.05, "CIN": 1.04, "TEX": 1.00, "NYY": 1.03,
    "LAD": 0.98, "SD": 0.96, "SEA": 0.95, "MIA": 0.97, "TB": 0.98,
    "HOU": 1.02, "ATL": 1.02, "CHC": 1.01, "DET": 0.99,
}
DOME_TEAMS = {"TB", "TOR", "HOU", "TEX", "MIA", "ARI", "MIL"}


def _parse_ip(ip: str | None) -> float:
    """'85.2' innings -> 85.667 (the .1/.2 are thirds of an inning)."""
    if not ip:
        return 0.0
    whole, _, frac = ip.partition(".")
    try:
        return int(whole or 0) + (int(frac) / 3 if frac else 0.0)
    except ValueError:
        return 0.0


async def _get(client: httpx.AsyncClient, path: str, **params) -> dict:
    r = await client.get(f"{BASE}{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


async def fetch_team_abbrs(client: httpx.AsyncClient, season: int) -> dict[int, str]:
    data = await _get(client, "/teams", sportId=1, season=season)
    return {t["id"]: t.get("abbreviation", str(t["id"])) for t in data.get("teams", [])}


async def fetch_pitcher_stats(
    client: httpx.AsyncClient, pid: int, season: int
) -> dict:
    """Season rate stats (for the projection) + last-5-start K totals (for the card)."""
    data = await _get(
        client,
        f"/people/{pid}",
        hydrate=f"stats(group=[pitching],type=[season,gameLog],season={season})",
    )

    season_stat: dict = {}
    last5: list[int] = []
    for block in data.get("people", [{}])[0].get("stats", []):
        kind = (block.get("type") or {}).get("displayName")
        splits = block.get("splits", [])
        if kind == "season" and splits:
            season_stat = splits[0].get("stat", {})
        elif kind == "gameLog":
            ks = [int(s.get("stat", {}).get("strikeOuts", 0) or 0) for s in splits]
            last5 = ks[-5:]  # gameLog is chronological, oldest -> newest

    so = float(season_stat.get("strikeOuts", 0) or 0)
    ip = _parse_ip(season_stat.get("inningsPitched"))
    gs = int(season_stat.get("gamesStarted", 0) or 0)
    k9 = (so * 9.0 / ip) if ip > 0 else 7.5
    ipgs = (ip / gs) if gs > 0 else 5.0
    stats = PitcherStats(k9=round(k9, 2), innings_per_start=round(ipgs, 2), games_started=gs)
    return {"stats": stats, "last5_k": last5}


async def fetch_team_k_rate(client: httpx.AsyncClient, team_id: int, season: int) -> float:
    try:
        data = await _get(
            client, f"/teams/{team_id}/stats", season=season, group="hitting", stats="season"
        )
        stat = data["stats"][0]["splits"][0]["stat"]
        so = float(stat.get("strikeOuts", 0) or 0)
        pa = float(stat.get("plateAppearances", 0) or 0)
        return so / pa if pa > 0 else LEAGUE_K_RATE
    except (httpx.HTTPError, KeyError, IndexError):
        return LEAGUE_K_RATE


async def fetch_raw_slate(date: str, season: int) -> list[dict]:
    """One probable-pitcher entry per starting pitcher on `date` (YYYY-MM-DD)."""
    async with httpx.AsyncClient() as client:
        sched = await _get(
            client, "/schedule", sportId=1, date=date, hydrate="probablePitcher"
        )
        abbrs = await fetch_team_abbrs(client, season)

        games = [g for d in sched.get("dates", []) for g in d.get("games", [])]

        # Collect starters: (pitcher, his team id, opp team id, is_home, game)
        starters: list[dict] = []
        for g in games:
            home = g["teams"]["home"]
            away = g["teams"]["away"]
            home_abbr = abbrs.get(home["team"]["id"], "")
            for side_key, opp_key, is_home in (("home", "away", True), ("away", "home", False)):
                side = g["teams"][side_key]
                opp = g["teams"][opp_key]
                pp = side.get("probablePitcher")
                if not pp:
                    continue
                starters.append(
                    {
                        "pid": pp["id"],
                        "pitcher": pp["fullName"],
                        "team_id": side["team"]["id"],
                        "team": abbrs.get(side["team"]["id"], "?"),
                        "opp_id": opp["team"]["id"],
                        "opponent": abbrs.get(opp["team"]["id"], "?"),
                        "is_home": is_home,
                        "game_time": g["gameDate"],
                        "park_abbr": home_abbr,
                    }
                )

        # Fetch pitcher stats + opponent K rates concurrently (de-dup teams).
        opp_ids = {s["opp_id"] for s in starters}
        krate_tasks = {tid: fetch_team_k_rate(client, tid, season) for tid in opp_ids}
        krates = dict(zip(krate_tasks.keys(), await asyncio.gather(*krate_tasks.values())))

        stats_list = await asyncio.gather(
            *(fetch_pitcher_stats(client, s["pid"], season) for s in starters)
        )

    out: list[dict] = []
    for s, sd in zip(starters, stats_list):
        park = s["park_abbr"]
        out.append(
            {
                **s,
                "stats": sd["stats"],
                "last5_k": sd["last5_k"],
                "opp_k_rate": krates.get(s["opp_id"], LEAGUE_K_RATE),
                "park_factor": PARK_FACTORS.get(park, 1.0),
                "is_dome": park in DOME_TEAMS,
            }
        )
    return out
