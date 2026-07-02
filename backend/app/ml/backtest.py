"""Backtest the projection model on held-out starts.

Two things that make the on-screen numbers trustworthy:

1. **Projection grading** — MAE and bias overall and by projection bucket
   (does the model systematically under-project high-K aces?).

2. **Probability calibration** — the app turns a projection interval into
   P(strikeouts > line) via a normal CDF, and that probability drives EV/Kelly.
   Here we check: when the model says "68% over", does it hit ~68%? If not, we
   learn a single variance-scale correction (minimizing log-loss) and report the
   calibration before/after. The chosen scale is written to models/calibration.json
   and applied at serve time (backend `prob_for_side`, frontend `probForSide`).

Uses the exact held-out test split from train.py (never seen during fit), so
this is genuine out-of-sample evaluation with no extra data fetch.

Run: python -m app.ml.backtest   (from backend/, venv active, after train)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from .features import FEATURES, TARGET

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "training.csv"
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"

# Half-point offsets from the projection at which we probe P(over) — spans the
# realistic range of posted strikeout lines, avoids pushes (x.5 lines only).
LINE_OFFSETS = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]


def _splits() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reproduce train.py's fit/cal/test split; return (calibration, test).

    The calibration slice is used to LEARN the corrections; the test slice
    (never touched by fit or calibration) is used to REPORT them.
    """
    df = pd.read_csv(DATA_PATH)
    _, tmp = train_test_split(df, test_size=0.4, random_state=42)
    cal, test = train_test_split(tmp, test_size=0.5, random_state=42)
    return cal.reset_index(drop=True), test.reset_index(drop=True)


def _prob_over(proj: float, low: float, high: float, line: float, scale: float) -> float:
    sd = max((high - low) / 2 / 1.645, 0.5) * scale
    z = (line - proj) / (sd * math.sqrt(2))
    return 1.0 - 0.5 * (1 + math.erf(z))


def _pairs(df: pd.DataFrame, proj, low, high, scale: float):
    """(predicted_prob, actual_over) across probe lines for every start."""
    p, y = [], []
    actual = df[TARGET].to_numpy()
    for i in range(len(df)):
        for off in LINE_OFFSETS:
            line = round(proj[i]) + off
            if line <= 0:
                continue
            p.append(_prob_over(proj[i], low[i], high[i], line, scale))
            y.append(1.0 if actual[i] > line else 0.0)
    return np.array(p), np.array(y)


def _log_loss(p, y, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _reliability(p, y, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    rows, ece = [], 0.0
    for b in range(bins):
        lo, hi = edges[b], edges[b + 1]
        mask = (p >= lo) & (p < hi) if b < bins - 1 else (p >= lo) & (p <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        pred, emp = float(p[mask].mean()), float(y[mask].mean())
        ece += abs(pred - emp) * n
        rows.append((f"{lo:.1f}-{hi:.1f}", n, round(pred, 3), round(emp, 3)))
    return rows, ece / len(p)


def _predict(df: pd.DataFrame, q05, q50, q95, widen: float):
    X = df[FEATURES]
    proj = q50.predict(X)
    low = np.maximum(0.0, q05.predict(X) - widen)
    high = q95.predict(X) + widen
    return proj, low, high


def _bias_table(proj, actual, title: str) -> None:
    err = proj - actual
    print(f"{title}: MAE={np.mean(np.abs(err)):.3f}  bias(mean proj-actual)={np.mean(err):+.3f}")
    buckets = pd.cut(pd.Series(proj), [0, 4, 5, 6, 7, 20], right=False)
    g = pd.DataFrame({"proj": proj, "actual": actual, "b": buckets})
    for b, sub in g.groupby("b", observed=True):
        print(f"    proj {str(b):10} n={len(sub):4d}  mean_proj={sub.proj.mean():.2f}  "
              f"mean_actual={sub.actual.mean():.2f}  bias={sub.proj.mean()-sub.actual.mean():+.2f}")


def main() -> None:
    cal_df, test_df = _splits()
    q05 = joblib.load(MODELS_DIR / "q05.joblib")
    q50 = joblib.load(MODELS_DIR / "q50.joblib")
    q95 = joblib.load(MODELS_DIR / "q95.joblib")
    widen = json.loads((MODELS_DIR / "calibration.json").read_text()).get("cqr_widen", 0.0)

    proj_c, low_c, high_c = _predict(cal_df, q05, q50, q95, widen)
    proj_t, low_t, high_t = _predict(test_df, q05, q50, q95, widen)
    act_c, act_t = cal_df[TARGET].to_numpy(), test_df[TARGET].to_numpy()

    # --- 1. projection de-bias (fit on cal, report on test) -------------------
    # The model's spread is too wide at the tails; a linear map pulls extremes
    # back toward reality (regression to the mean the model missed).
    slope, intercept = np.polyfit(proj_c, act_c, 1)

    def correct(p):
        return intercept + slope * p

    print("=== Projection grading (held-out test) ===")
    _bias_table(proj_t, act_t, "  RAW  ")
    print(f"  learned linear correction: proj' = {intercept:+.3f} + {slope:.3f}*proj  (fit on calibration)")
    _bias_table(correct(proj_t), act_t, "  DEBIASED")

    # Recenter the interval by the same per-start shift (preserves CQR width).
    shift_t = correct(proj_t) - proj_t
    low_t2, high_t2 = low_t + shift_t, high_t + shift_t
    proj_t2 = correct(proj_t)
    # same correction on the calibration slice, for scale selection
    shift_c = correct(proj_c) - proj_c
    proj_c2, low_c2, high_c2 = correct(proj_c), low_c + shift_c, high_c + shift_c

    # --- 2. probability calibration on the DEBIASED projection ----------------
    print("\n=== Probability calibration: P(strikeouts > line) [after de-bias] ===")
    p_raw, y_raw = _pairs(test_df, proj_t2, low_t2, high_t2, scale=1.0)
    _, ece_raw = _reliability(p_raw, y_raw)
    ll_raw = _log_loss(p_raw, y_raw)

    scales = np.arange(0.60, 1.81, 0.05)
    best = float(min(scales, key=lambda s: _log_loss(*_pairs(cal_df, proj_c2, low_c2, high_c2, s))))
    pb, yb = _pairs(test_df, proj_t2, low_t2, high_t2, best)
    rows, ece_best = _reliability(pb, yb)
    ll_best = _log_loss(pb, yb)

    print(f"  scale=1.00:      logloss={ll_raw:.4f}  ECE={ece_raw:.4f}")
    print(f"  scale={best:.2f} (best on cal): logloss={ll_best:.4f}  ECE={ece_best:.4f}")
    print("\n  reliability @ chosen scale (pred vs empirical over-rate):")
    print("    bin        n     pred   emp")
    for name, n, pred, emp in rows:
        print(f"    {name:9} {n:5d}  {pred:.3f} {emp:.3f}")

    out = {
        "cqr_widen": round(float(widen), 3),
        "proj_slope": round(float(slope), 4),
        "proj_intercept": round(float(intercept), 4),
        "prob_sigma_scale": round(best, 3),
    }
    (MODELS_DIR / "calibration.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote corrections -> models/calibration.json: {out}")


if __name__ == "__main__":
    main()
