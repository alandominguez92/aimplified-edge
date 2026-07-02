"""Implied-probability / EV / Kelly math.

A line-for-line port of the frontend `src/lib/odds.ts`. Keeping the two in sync
means the browser-side preview and the server agree to the cent. This module is
also the reference the future C++ engine (kelly.cpp) will be tested against.
"""
from __future__ import annotations


def american_to_decimal(american: int) -> float:
    """American odds -> decimal payout multiplier (-120 -> 1.833, +130 -> 2.30)."""
    return 1 + american / 100 if american > 0 else 1 + 100 / abs(american)


def implied_prob(american: int) -> float:
    """Implied probability from American odds, INCLUDING the book's vig."""
    if american > 0:
        return 100 / (american + 100)
    return abs(american) / (abs(american) + 100)


def novig(odds_a: int, odds_b: int) -> float:
    """Vig-free fair probability for side A of a two-way market."""
    a = implied_prob(odds_a)
    b = implied_prob(odds_b)
    return a / (a + b)


def expected_value(p: float, odds: int) -> float:
    """EV per 1 unit staked. 0.05 == +5% EV."""
    dec = american_to_decimal(odds)
    return p * (dec - 1) - (1 - p)


def kelly_fraction(p: float, odds: int) -> float:
    """Full-Kelly fraction of bankroll; clamped at 0 (never stake -EV)."""
    b = american_to_decimal(odds) - 1
    if b <= 0:
        return 0.0
    return max(0.0, (p * b - (1 - p)) / b)


def decimal_to_american(dec: float) -> int:
    b = dec - 1
    return round(b * 100) if b >= 1 else round(-100 / b)
