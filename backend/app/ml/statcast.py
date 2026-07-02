"""Statcast plate-discipline features from Baseball Savant (via pybaseball).

We use season-level **whiff%** (swing-and-miss rate), pitch-weighted per pitcher,
as a strikeout-skill signal. It's keyed by MLBAM player id — the same ids MLB
StatsAPI uses — so it joins to our training/serve data with no crosswalk.

Used as a *prior-season* feature (season-1), which is leakage-free: a pitcher's
skill entering a season is known before any of that season's starts, and whiff%
is far more stable start-to-start than raw strikeout counts.

NOTE: pybaseball's FanGraphs scrapers are currently broken (403); Savant's
arsenal-stats leaderboard is the reliable source. Run:
    python -m app.ml.statcast     (from backend/, venv active)
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

# Prior seasons needed: training spans 2024-25 (needs 2023-24 priors) and serving
# the 2026 season needs the 2025 prior.
SEASONS = [2023, 2024, 2025]
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "statcast_whiff.csv"

# League-average whiff% fallback for pitchers with no prior-season Statcast row.
DEFAULT_WHIFF = 24.0


def build_table() -> Path:
    from pybaseball import statcast_pitcher_arsenal_stats

    frames = []
    for season in SEASONS:
        df = statcast_pitcher_arsenal_stats(season)
        # pitch-weighted whiff% per pitcher
        g = df.groupby("player_id").apply(
            lambda s: pd.Series(
                {
                    "whiff_pct": (s["whiff_percent"] * s["pitches"]).sum() / s["pitches"].sum(),
                    "n_pitches": s["pitches"].sum(),
                }
            ),
            include_groups=False,
        ).reset_index()
        g["season"] = season
        frames.append(g)
        print(f"  season {season}: {len(g)} pitchers")

    out = pd.concat(frames, ignore_index=True)[["player_id", "season", "whiff_pct", "n_pitches"]]
    out["player_id"] = out["player_id"].astype(int)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"wrote {len(out)} rows -> {OUT_PATH}")
    return OUT_PATH


_cache: dict[tuple[int, int], float] | None = None


def load_whiff() -> dict[tuple[int, int], float]:
    """{(player_id, season): whiff_pct}. Empty if the table hasn't been built."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        df = pd.read_csv(OUT_PATH)
        _cache = {
            (int(r.player_id), int(r.season)): float(r.whiff_pct)
            for r in df.itertuples()
        }
    except (FileNotFoundError, OSError):
        _cache = {}
    return _cache


def prior_whiff(player_id: int | None, season: int) -> float:
    """Prior-season (season-1) whiff% for a pitcher, else the league default."""
    if player_id is None:
        return DEFAULT_WHIFF
    return load_whiff().get((int(player_id), season - 1), DEFAULT_WHIFF)


if __name__ == "__main__":
    build_table()
