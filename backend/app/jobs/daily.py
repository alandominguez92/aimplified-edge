"""Daily maintenance job — keeps the track record accruing unattended.

Each run: (1) builds today's slate, which logs any new recommendations as picks
and records a line snapshot (improving closing-line/CLV capture), and (2) grades
open picks whose games have finished. Designed to be run several times a day by
Windows Task Scheduler, independent of the dev server.

Run manually:  python -m app.jobs.daily   (from backend/, venv active)
"""
from __future__ import annotations

import asyncio
import datetime
from pathlib import Path

from ..config import get_settings
from ..services.results import grade_open_picks, record_summary
from ..services.slate import build_slate

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "jobs.log"


def _log(msg: str) -> None:
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


async def main() -> None:
    settings = get_settings()
    today = datetime.date.today().isoformat()
    try:
        props = await build_slate(today, settings.mlb_season)  # logs picks + snapshot
        recs = sum(1 for p in props if p.projection.recommended_side and p.books)
        graded = await grade_open_picks(today)
        r = record_summary()
        _log(
            f"OK  slate={len(props)} starters, {recs} flagged  |  graded={graded}  |  "
            f"record {r['record']} ROI {r['roiPct']} open {r['openPicks']} "
            f"CLV {r['avgClv']}  (odds={'on' if settings.odds_enabled else 'off'})"
        )
    except Exception as e:  # keep the scheduled task green; just log the failure
        _log(f"ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
