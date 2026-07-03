"""SportsGameOdds integration — pitcher strikeout props (api.sportsgameodds.com).

Free-tier friendly: one or two paginated /v2/events calls per slate, gated on
SPORTSGAMEODDS_API_KEY. Any failure degrades to "no odds" so the slate still
renders from StatsAPI + projections.

Odds model (per their docs): each event has an `odds` map keyed by
`{statID}-{statEntityID}-{periodID}-{betTypeID}-{sideID}`, e.g.
`batting_strikeouts-CODY_BELLINGER_1_MLB-game-ou-under`. Each entry carries a
`byBookmaker` map of `{ bookId: { odds, overUnder, available } }`.

We match props to our probable *pitchers* by the player name encoded in
statEntityID, so we don't depend on the exact strikeout statID spelling.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

import httpx

from ..config import get_settings


def _day_window(date: str) -> tuple[str, str]:
    """UTC window for a US 'baseball day'.

    MLB games for date D run from late morning ET (~15:00Z on D) through late
    West-Coast starts that cross midnight UTC (up to ~06:00Z on D+1). A naive
    {D}T00:00:00Z–{D}T23:59:59Z window drops those late games (Dodgers, Padres,
    Angels…). We use [D 10:00Z, D+1 10:00Z] to capture the whole slate while
    excluding the prior day's tail and the next day's games.
    """
    nxt = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    return f"{date}T10:00:00Z", f"{nxt}T09:59:59Z"

BASE = "https://api.sportsgameodds.com/v2/events"

# SportsGameOdds bookmaker ids -> our display names. The free tier surfaces
# draftkings/fanduel/caesars/espnbet/bovada (BetMGM/Underdog generally absent);
# we map all we recognize so the prediction card can shop the best price, while
# the table renders whichever of these it has columns for.
BOOK_MAP = {
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
    "caesars": "Caesars",
    "espnbet": "ESPN BET",
    "betmgm": "BetMGM",
    "bovada": "Bovada",
}

_PLAYER_SUFFIX = re.compile(r"_\d+_[A-Z]+$")  # strip trailing "_1_MLB"


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/punctuation for matching across data sources."""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(c for c in n.lower() if c.isalnum() or c == " ").strip()


def _name_from_entity(entity_id: str) -> str:
    """'JACOB_DEGROM_1_MLB' -> normalized 'jacob degrom'."""
    base = _PLAYER_SUFFIX.sub("", entity_id)
    return normalize_name(base.replace("_", " "))


_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _initial_last(norm_name: str) -> str | None:
    """'matt liberatore' / 'matthew liberatore' -> 'm liberatore'.

    Keys a player by first-initial + last name so first-name variants (Matt vs
    Matthew, Mike vs Michael) collapse together, while different first names that
    share a surname (Eury vs Martín Pérez -> 'e perez' vs 'm perez') stay apart.
    """
    parts = [p for p in norm_name.split() if p not in _NAME_SUFFIXES]
    if len(parts) < 2:
        return None
    return f"{parts[0][0]} {parts[-1]}"


def match_books(odds: dict[str, dict], full_name: str) -> dict:
    """Find a pitcher's book odds, tolerant of first-name variations.

    1. Exact normalized full-name match.
    2. Fallback: unambiguous first-initial + last-name match (skipped if two
       SGO players collide on that key, to avoid a wrong attribution).
    """
    nm = normalize_name(full_name)
    if nm in odds:
        return odds[nm]

    key = _initial_last(nm)
    if not key:
        return {}
    candidates = [k for k in odds if _initial_last(k) == key]
    return odds[candidates[0]] if len(candidates) == 1 else {}


def _parse_odds(value) -> int | None:
    try:
        return int(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None


async def fetch_strikeout_props(date: str) -> dict[str, dict]:
    """{ normalized_pitcher_name: { BookName: {'over': {line,odds}, 'under': {...}} } }."""
    settings = get_settings()
    if not settings.odds_enabled:
        return {}

    starts_after, starts_before = _day_window(date)
    headers = {"x-api-key": settings.sgo_api_key}
    params = {
        "leagueID": "MLB",
        "oddsAvailable": "true",
        "startsAfter": starts_after,
        "startsBefore": starts_before,
        # Market filter: only pitcher strikeout O/U (the opposing 'under' comes
        # along via includeOpposingOddIDs). Cuts the payload ~99% vs all props,
        # which keeps polling within the free-tier object budget.
        "oddIDs": "pitching_strikeouts-PLAYER_ID-game-ou-over",
        "includeOpposingOddIDs": "true",
        "limit": "100",
    }

    result: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=25, headers=headers) as client:
            cursor: str | None = None
            for _ in range(5):  # page cap — protects the free-tier object budget
                if cursor:
                    params["cursor"] = cursor
                r = await client.get(BASE, params=params)
                if r.status_code != 200:
                    break
                payload = r.json()
                for event in payload.get("data", []):
                    _ingest_event(event, result)
                cursor = payload.get("nextCursor")
                if not cursor:
                    break
    except (httpx.HTTPError, ValueError, KeyError):
        return result

    return result


async def fetch_hits_slate(date: str) -> dict[str, dict]:
    """Batter hit props for `date`. Unlike pitchers, the slate itself comes from
    the odds feed: { normalized_batter: {team, opponent, isHome, books} }.

    Team/matchup are read from each event's `players` map (teamID) + `teams`.
    """
    settings = get_settings()
    if not settings.odds_enabled:
        return {}

    starts_after, starts_before = _day_window(date)
    headers = {"x-api-key": settings.sgo_api_key}
    params = {
        "leagueID": "MLB",
        "oddsAvailable": "true",
        "startsAfter": starts_after,
        "startsBefore": starts_before,
        "oddIDs": "batting_hits-PLAYER_ID-game-ou-over",
        "includeOpposingOddIDs": "true",
        "limit": "100",
    }

    result: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=25, headers=headers) as client:
            cursor: str | None = None
            for _ in range(5):
                if cursor:
                    params["cursor"] = cursor
                r = await client.get(BASE, params=params)
                if r.status_code != 200:
                    break
                payload = r.json()
                for event in payload.get("data", []):
                    _ingest_hits_event(event, result)
                cursor = payload.get("nextCursor")
                if not cursor:
                    break
    except (httpx.HTTPError, ValueError, KeyError):
        return result
    return result


def _team_abbrs(event: dict) -> dict[str, tuple[str, str, bool]]:
    """teamID -> (own abbr, opponent abbr, is_home) for the two teams in a game."""
    teams = event.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    h_abbr = (home.get("names") or {}).get("short", "?")
    a_abbr = (away.get("names") or {}).get("short", "?")
    out = {}
    if home.get("teamID"):
        out[home["teamID"]] = (h_abbr, a_abbr, True)
    if away.get("teamID"):
        out[away["teamID"]] = (a_abbr, h_abbr, False)
    return out


def _ingest_hits_event(event: dict, result: dict[str, dict]) -> None:
    players = event.get("players") or {}
    team_map = _team_abbrs(event)
    for odd in (event.get("odds") or {}).values():
        if (
            odd.get("betTypeID") != "ou"
            or odd.get("periodID") != "game"
            or "hits" not in (odd.get("statID") or "")
        ):
            continue
        side = odd.get("sideID")
        if side not in ("over", "under"):
            continue
        entity = odd.get("statEntityID") or ""
        if entity in ("home", "away", "all"):
            continue

        name = _name_from_entity(entity)
        if not name:
            continue
        pdata = players.get(entity) or {}
        team_id = pdata.get("teamID")
        team, opp, is_home = team_map.get(team_id, ("?", "?", False))
        display = pdata.get("name") or name.title()
        status = event.get("status") or {}
        game_time = status.get("startsAt", "")
        # Once the game is over the batter is done — flag it so the slate drops
        # finished players (SGO sets completed/ended/finalized on final events).
        finished = bool(
            status.get("completed") or status.get("ended") or status.get("finalized")
        )
        fallback_line = odd.get("bookOverUnder")

        entry = result.setdefault(
            name,
            {"name": display, "team": team, "opponent": opp, "isHome": is_home,
             "gameTime": game_time, "finished": finished, "books": {}},
        )
        for book_id, bk in (odd.get("byBookmaker") or {}).items():
            book = BOOK_MAP.get(book_id)
            if not book or bk.get("available") is False:
                continue
            price = _parse_odds(bk.get("odds"))
            if price is None:
                continue
            try:
                line = float(bk.get("overUnder", fallback_line))
            except (TypeError, ValueError):
                continue
            entry["books"].setdefault(book, {})[side] = {"line": line, "odds": price}


def _ingest_event(event: dict, result: dict[str, dict]) -> None:
    odds = event.get("odds") or {}
    for odd in odds.values():
        if (
            odd.get("betTypeID") != "ou"
            or odd.get("periodID") != "game"
            or "strikeouts" not in (odd.get("statID") or "")
        ):
            continue
        side = odd.get("sideID")
        if side not in ("over", "under"):
            continue
        entity = odd.get("statEntityID") or ""
        if entity in ("home", "away", "all"):
            continue  # team total, not a player prop

        name = _name_from_entity(entity)
        if not name:
            continue
        fallback_line = odd.get("bookOverUnder")

        for book_id, bk in (odd.get("byBookmaker") or {}).items():
            book = BOOK_MAP.get(book_id)
            if not book or bk.get("available") is False:
                continue
            price = _parse_odds(bk.get("odds"))
            if price is None:
                continue
            try:
                line = float(bk.get("overUnder", fallback_line))
            except (TypeError, ValueError):
                continue
            entry = result.setdefault(name, {})
            book_entry = entry.setdefault(book, {})
            book_entry[side] = {"line": line, "odds": price}
