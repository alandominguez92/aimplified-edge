"""Serve-time strikeout projection from the trained quantile models.

Loads the q05/q50/q95 gradient-boosted models + the CQR calibration constant and
produces the same dict shape as the heuristic `projection.project()`, so the
slate assembler can use whichever is available. If the model artifacts are
missing (e.g. training hasn't been run), `available()` is False and the slate
falls back to the heuristic.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Silence joblib's core-count probe (it shells out to `wmic`, absent on newer Win).
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))

import joblib  # noqa: E402
import pandas as pd  # noqa: E402

from ..ml.features import FEATURES, feature_row, to_vector  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"

_models: dict | None = None
_widen: float = 0.0
# Projection de-bias learned by backtest.py: proj' = intercept + slope*proj.
# Defaults are the identity so an un-backtested model is served unchanged.
_slope: float = 1.0
_intercept: float = 0.0


def _load() -> dict | None:
    global _models, _widen, _slope, _intercept
    if _models is not None:
        return _models
    try:
        bundle = {
            "q05": joblib.load(MODELS_DIR / "q05.joblib"),
            "q50": joblib.load(MODELS_DIR / "q50.joblib"),
            "q95": joblib.load(MODELS_DIR / "q95.joblib"),
        }
        cal = json.loads((MODELS_DIR / "calibration.json").read_text())
        _widen = float(cal.get("cqr_widen", 0.0))
        _slope = float(cal.get("proj_slope", 1.0))
        _intercept = float(cal.get("proj_intercept", 0.0))
        _models = bundle
    except (FileNotFoundError, OSError, ValueError):
        _models = {}  # mark "tried, unavailable"
    return _models or None


def available() -> bool:
    return _load() is not None


def metrics() -> dict | None:
    try:
        return json.loads((MODELS_DIR / "metrics.json").read_text())
    except (FileNotFoundError, OSError, ValueError):
        return None


def calibration() -> dict | None:
    try:
        return json.loads((MODELS_DIR / "calibration.json").read_text())
    except (FileNotFoundError, OSError, ValueError):
        return None


def _confidence(projected: float, low: float, high: float, games_started: int) -> float:
    """Spread-aware confidence: tighter *relative* interval + more starts = higher.

    Strikeout intervals are wide in absolute terms, so we score the interval
    relative to the projection (a coefficient-of-variation proxy) and add a small
    sample-size bonus. Kept in [0.50, 0.85] to avoid false precision."""
    rel = (high - low) / max(projected, 1.0)
    sample_bonus = 0.015 * min(games_started, 20)
    raw = 0.92 - 0.16 * rel + sample_bonus
    return max(0.50, min(0.85, raw))


def project(
    *,
    k9: float,
    ip_per_start: float,
    recent_k: float,
    games_started: int,
    opp_k_rate: float,
    park_factor: float,
    is_home: bool,
    whiff_prev: float,
) -> dict:
    """Predicted K (median) + a CQR-calibrated ~90% interval + a confidence score."""
    models = _load()
    if not models:
        raise RuntimeError("ML models not loaded")

    row = feature_row(
        k9=k9, ip_per_start=ip_per_start, recent_k=recent_k,
        games_started=games_started, opp_k_rate=opp_k_rate,
        park_factor=park_factor, is_home=is_home, whiff_prev=whiff_prev,
    )
    # Predict with named columns (as fitted) to avoid sklearn feature-name warnings.
    X = pd.DataFrame([to_vector(row)], columns=FEATURES)
    p50 = float(models["q50"].predict(X)[0])
    lo = float(models["q05"].predict(X)[0]) - _widen
    hi = float(models["q95"].predict(X)[0]) + _widen

    # De-bias the point estimate (backtest-learned) and shift the interval by the
    # same amount so its calibrated width is preserved.
    corrected = _intercept + _slope * p50
    shift = corrected - p50
    p50, lo, hi = corrected, lo + shift, hi + shift

    # Keep the band sane and ordered around the point estimate.
    p50 = max(0.0, p50)
    lo = max(0.0, min(lo, p50))
    hi = max(hi, p50)

    confidence = _confidence(p50, lo, hi, games_started)

    return {
        "projected_k": round(p50, 1),
        "low": round(lo, 1),
        "high": round(hi, 1),
        "confidence": round(confidence, 2),
    }


# touch FEATURES so linters keep the import (schema is the single source of truth)
_ = FEATURES
