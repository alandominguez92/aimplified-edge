"""Baseline strikeout projection + probability helpers.

This is a transparent *heuristic*, not the eventual ML model (that's a later
milestone). It turns season-to-date pitcher rate stats and the opponent's
strikeout tendency into a projected K total with a confidence interval, then
into a probability of clearing a given line. The ML engine will later replace
`project()` while keeping the same output shape.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# League-average hitter strikeout rate (K per plate appearance). Used to scale a
# pitcher's projection up or down for the opponent they face.
LEAGUE_K_RATE = 0.224


@dataclass
class PitcherStats:
    k9: float            # strikeouts per 9 innings, season to date
    innings_per_start: float
    games_started: int


def _erf(x: float) -> float:
    # math.erf exists; kept as a thin alias so the formula mirrors odds.ts/projection.ts.
    return math.erf(x)


def _normal_cdf(x: float, mean: float, sd: float) -> float:
    if sd <= 0:
        return 1.0 if x >= mean else 0.0
    return 0.5 * (1 + _erf((x - mean) / (sd * math.sqrt(2))))


def project(stats: PitcherStats, opp_k_rate: float, park_factor: float) -> dict:
    """Return projected K plus a ~90% interval and a confidence score."""
    exp_ip = min(6.5, max(3.5, stats.innings_per_start or 5.0))
    opp_factor = max(0.85, min(1.15, (opp_k_rate or LEAGUE_K_RATE) / LEAGUE_K_RATE))

    projected = (stats.k9 / 9.0) * exp_ip * opp_factor * park_factor
    projected = max(0.5, projected)

    # Strikeouts are roughly Poisson; widen slightly for model uncertainty.
    sd = max(0.6, math.sqrt(projected) * 1.15)
    low = max(0.0, projected - 1.645 * sd)
    high = projected + 1.645 * sd

    # More starts -> more confidence, capped.
    confidence = min(0.85, 0.50 + stats.games_started * 0.022)

    return {
        "projected_k": round(projected, 1),
        "low": round(low, 1),
        "high": round(high, 1),
        "confidence": round(confidence, 2),
        "_sd": sd,
    }


def prob_over(projected_k: float, low: float, high: float, line: float) -> float:
    """P(strikeouts > line), recovering sigma from the reported 90% interval."""
    sd = max((high - low) / 2 / 1.645, 0.5)
    return 1 - _normal_cdf(line, projected_k, sd)


def prob_for_side(projected_k: float, low: float, high: float, line: float, side: str) -> float:
    over = prob_over(projected_k, low, high, line)
    return over if side == "over" else 1 - over
