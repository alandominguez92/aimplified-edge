"""Feature contract shared by training and serving.

Both the dataset builder and the live projection must produce these features in
this exact order, computed from information known *before* the start (no
leakage). Keeping the list in one place is what guarantees train/serve parity.
"""
from __future__ import annotations

# Order matters: model input columns are positional.
FEATURES: list[str] = [
    "k9",             # season-to-date strikeouts per 9 innings
    "ip_per_start",   # season-to-date innings per start
    "recent_k",       # mean strikeouts over the last (<=5) starts
    "games_started",  # starts so far (a sample-size signal)
    "opp_k_rate",     # opponent season strikeout rate (K / PA)
    "park_factor",    # ballpark K factor (1.00 = neutral)
    "is_home",        # 1 if pitching at home
    "whiff_prev",     # Statcast prior-season whiff% (skill prior, leakage-free)
]

TARGET = "strikeouts"


def feature_row(
    *,
    k9: float,
    ip_per_start: float,
    recent_k: float,
    games_started: int,
    opp_k_rate: float,
    park_factor: float,
    is_home: bool,
    whiff_prev: float,
) -> dict[str, float]:
    """Assemble a single feature dict in the canonical schema."""
    return {
        "k9": float(k9),
        "ip_per_start": float(ip_per_start),
        "recent_k": float(recent_k),
        "games_started": float(games_started),
        "opp_k_rate": float(opp_k_rate),
        "park_factor": float(park_factor),
        "is_home": 1.0 if is_home else 0.0,
        "whiff_prev": float(whiff_prev),
    }


def to_vector(row: dict[str, float]) -> list[float]:
    return [row[f] for f in FEATURES]
