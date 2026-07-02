"""Forward result-logging: track flagged picks and grade them for real ROI/CLV.

Real bet ROI and closing-line value need *odds at the time you'd have bet* and
the *actual outcome*. We can't backfill historical odds (SGO free is current-day
only), so we log every recommendation as it's flagged and grade it once the game
is final — building a genuine track record going forward.

- `log_picks`   — called on each slate build; records new recommendations.
- `grade_open_picks` — fetches finished-game strikeout totals and settles picks.
- `record_summary`   — aggregate hit rate / ROI / CLV over graded picks.
"""
from __future__ import annotations

import httpx

from .. import db
from ..engine import odds_math
from ..engine.projection import prob_for_side
from ..schemas import PitcherProp
from . import mlb_statsapi

# --- pure grading math (unit-testable) -------------------------------------


def settle(side: str, line: float, actual_k: int) -> str:
    """'win' | 'loss' | 'push' for a side, given the line and the actual result."""
    if actual_k == line:
        return "push"
    over_hit = actual_k > line
    won = over_hit if side == "over" else not over_hit
    return "win" if won else "loss"


def profit_units(result: str, odds: int, stake: float = 1.0) -> float:
    """Net units at the given American odds (flat stake)."""
    if result == "push":
        return 0.0
    if result == "loss":
        return -stake
    return stake * (odds_math.american_to_decimal(odds) - 1)


def clv(side: str, line_at_pick: float, closing_line: float) -> float:
    """Closing-line value in Ks: positive = the line moved in our favor.

    An over wants the closing line lower; an under wants it higher."""
    delta = line_at_pick - closing_line
    return delta if side == "over" else -delta


# --- best available price (server mirror of PredictionCard.bestPrice) --------


def _best_price(prop: PitcherProp, side: str):
    best = None
    for b in prop.books:
        s = getattr(b, side)
        if s is None:
            continue
        if best is None or odds_math.american_to_decimal(s.odds) > odds_math.american_to_decimal(best[1]):
            best = (s.line, s.odds, b.book)
    return best  # (line, odds, book) or None


# --- logging ----------------------------------------------------------------


def log_picks(date: str, props: list[PitcherProp], pitcher_ids: dict[str, int]) -> None:
    """Record every actionable recommendation (side + real market) as a pick."""
    for p in props:
        side = p.projection.recommended_side
        if not side or not p.books:
            continue
        price = _best_price(p, side)
        if price is None:
            continue
        line, odds, book = price
        true_p = prob_for_side(
            p.projection.projected_k, p.projection.low, p.projection.high, line, side
        )
        ev = odds_math.expected_value(true_p, odds)
        kelly = odds_math.kelly_fraction(true_p, odds)
        db.record_pick(
            {
                "day": date,
                "prop_id": p.id,
                "side": side,
                "pitcher": p.pitcher,
                "team": p.team,
                "opponent": p.opponent,
                "pitcher_id": pitcher_ids.get(p.id),
                "line": line,
                "odds": odds,
                "book": book,
                "projected_k": p.projection.projected_k,
                "edge": p.projection.edge,
                "true_prob": round(true_p, 4),
                "ev_pct": round(ev * 100, 2),
                "units": round(min(3.0, kelly / 4 * 10), 2),
                "created_ts": __import__("time").time(),
                "status": "open",
            }
        )


# --- grading ----------------------------------------------------------------


async def _actual_k(client: httpx.AsyncClient, pid: int, date: str) -> int | None:
    """Strikeouts for pitcher `pid` in the (final) game on `date`, else None."""
    season = int(date[:4])
    data = await mlb_statsapi._get(
        client, f"/people/{pid}",
        hydrate=f"stats(group=[pitching],type=[gameLog],season={season})",
    )
    for block in data.get("people", [{}])[0].get("stats", []):
        if (block.get("type") or {}).get("displayName") != "gameLog":
            continue
        for sp in block.get("splits", []):
            if sp.get("date") == date:
                return int(sp.get("stat", {}).get("strikeOuts", 0) or 0)
    return None


async def grade_open_picks(today: str) -> int:
    """Grade all open picks for games before `today`. Returns count graded."""
    pending = db.open_picks_before(today)
    if not pending:
        return 0

    graded = 0
    async with httpx.AsyncClient(timeout=25) as client:
        for pk in pending:
            if pk["pitcher_id"] is None:
                continue
            actual = await _actual_k(client, pk["pitcher_id"], pk["day"])
            if actual is None:
                continue  # game not final / pitcher scratched — try again later
            _, closing = db.open_and_current(pk["prop_id"], pk["day"])
            result = settle(pk["side"], pk["line"], actual)
            profit = profit_units(result, pk["odds"])
            c = clv(pk["side"], pk["line"], closing) if closing is not None else None
            db.grade_pick(
                pk["day"], pk["prop_id"], pk["side"],
                actual_k=actual, closing_line=closing, result=result,
                profit_units=round(profit, 4), clv=(round(c, 2) if c is not None else None),
            )
            graded += 1
    return graded


# --- aggregate --------------------------------------------------------------


def history() -> list[dict]:
    """Graded picks in settle order, with a running cumulative-units total."""
    rows = list(db.graded_picks())
    rows.sort(key=lambda r: (r["day"], r["graded_ts"] or 0))
    out: list[dict] = []
    cum = 0.0
    for r in rows:
        cum += r["profit_units"] or 0.0
        out.append({
            "day": r["day"],
            "pitcher": r["pitcher"],
            "side": r["side"],
            "line": r["line"],
            "odds": r["odds"],
            "result": r["result"],
            "profitUnits": round(r["profit_units"] or 0.0, 3),
            "clv": r["clv"],
            "cumulativeUnits": round(cum, 3),
        })
    return out


def record_summary() -> dict:
    rows = db.graded_picks()
    total, graded = db.counts()
    wins = sum(1 for r in rows if r["result"] == "win")
    losses = sum(1 for r in rows if r["result"] == "loss")
    pushes = sum(1 for r in rows if r["result"] == "push")
    decisions = wins + losses
    profit = sum(r["profit_units"] or 0.0 for r in rows)
    clvs = [r["clv"] for r in rows if r["clv"] is not None]

    return {
        "totalPicks": total,
        "openPicks": total - graded,
        "gradedPicks": graded,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "record": f"{wins}-{losses}" + (f"-{pushes}" if pushes else ""),
        "hitRate": round(wins / decisions, 3) if decisions else None,
        "unitsProfit": round(profit, 2),
        "roiPct": round(profit / decisions * 100, 1) if decisions else None,
        "avgClv": round(sum(clvs) / len(clvs), 2) if clvs else None,
    }
