"""Train the strikeout projection model.

Three gradient-boosted quantile regressors (5th / 50th / 95th percentile) give a
point projection (median) and a genuine ~90% prediction interval. We compare the
median model's error against simple baselines and check interval coverage, then
persist everything to backend/models/.

Run: python -m app.ml.train   (from backend/, venv active, after dataset build)
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

from .features import FEATURES, TARGET

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "training.csv"
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"
QUANTILES = {"q05": 0.05, "q50": 0.50, "q95": 0.95}


def _fit_quantile(X, y, q: float) -> HistGradientBoostingRegressor:
    model = HistGradientBoostingRegressor(
        loss="quantile",
        quantile=q,
        max_iter=400,
        learning_rate=0.05,
        max_leaf_nodes=31,
        min_samples_leaf=40,
        l2_regularization=0.1,
        random_state=42,
    )
    model.fit(X, y)
    return model


def main() -> None:
    df = pd.read_csv(DATA_PATH)
    X = df[FEATURES]
    y = df[TARGET]

    # Three-way split: fit / calibrate (for CQR) / test.
    X_fit, X_tmp, y_fit, y_tmp = train_test_split(X, y, test_size=0.4, random_state=42)
    X_cal, X_te, y_cal, y_te = train_test_split(X_tmp, y_tmp, test_size=0.5, random_state=42)

    models = {name: _fit_quantile(X_fit, y_fit, q) for name, q in QUANTILES.items()}

    # Conformalized quantile regression: widen the raw [q05, q95] band by a
    # constant so the interval hits ~90% coverage on held-out data. Without this
    # the quantile band undercovers (discrete, heavy-tailed strikeout counts).
    cal_lo, cal_hi = models["q05"].predict(X_cal), models["q95"].predict(X_cal)
    nonconformity = np.maximum(cal_lo - y_cal.to_numpy(), y_cal.to_numpy() - cal_hi)
    n = len(y_cal)
    level = min(1.0, (1 - 0.10) * (1 + 1 / n))
    q_widen = float(np.quantile(nonconformity, level))

    pred50 = models["q50"].predict(X_te)
    lo = models["q05"].predict(X_te) - q_widen
    hi = models["q95"].predict(X_te) + q_widen

    base_recent = X_te["recent_k"].to_numpy()
    base_rate = (X_te["k9"] / 9.0 * X_te["ip_per_start"]).to_numpy()

    mae_model = mean_absolute_error(y_te, pred50)
    mae_recent = mean_absolute_error(y_te, base_recent)
    mae_rate = mean_absolute_error(y_te, base_rate)
    yt = y_te.to_numpy()
    coverage_raw = float(np.mean(
        (yt >= models["q05"].predict(X_te)) & (yt <= models["q95"].predict(X_te))
    ))
    coverage_cqr = float(np.mean((yt >= lo) & (yt <= hi)))

    metrics = {
        "rows": int(len(df)),
        "test_rows": int(len(y_te)),
        "mae_model_median": round(mae_model, 3),
        "mae_baseline_recent5": round(mae_recent, 3),
        "mae_baseline_rate": round(mae_rate, 3),
        "improvement_vs_recent_pct": round((mae_recent - mae_model) / mae_recent * 100, 1),
        "improvement_vs_rate_pct": round((mae_rate - mae_model) / mae_rate * 100, 1),
        "interval_coverage_raw": round(coverage_raw, 3),
        "interval_coverage_cqr": round(coverage_cqr, 3),
        "cqr_widen": round(q_widen, 3),
        "features": FEATURES,
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        joblib.dump(model, MODELS_DIR / f"{name}.joblib")
    (MODELS_DIR / "calibration.json").write_text(json.dumps({"cqr_widen": q_widen}))
    (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print(json.dumps(metrics, indent=2))
    print(f"\nsaved models -> {MODELS_DIR}")


if __name__ == "__main__":
    main()
