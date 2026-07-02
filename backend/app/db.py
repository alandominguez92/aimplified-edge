"""Line-movement snapshots in SQLite (stdlib `sqlite3`, no ORM yet).

Sharp detection needs the *open* vs *current* line, which only exists if we
record lines over time. Every slate build stores a snapshot per prop; the open
line is the earliest snapshot for that prop today, the current line the latest.
A later milestone can migrate this to SQLAlchemy + Postgres for history/results.
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

# DATA_DIR lets a hosted deploy point the DB at a persistent volume (e.g. /data);
# defaults to the backend/ dir for local use.
_DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent)))
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_DIR / "data.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS line_snapshots (
    prop_key TEXT NOT NULL,
    day TEXT NOT NULL,
    ts REAL NOT NULL,
    line REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_prop_day ON line_snapshots (prop_key, day);

-- One row per model recommendation, logged when first flagged and graded once
-- the game is final. This is the forward track record (ROI / hit rate / CLV).
CREATE TABLE IF NOT EXISTS picks (
    day TEXT NOT NULL,
    prop_id TEXT NOT NULL,
    side TEXT NOT NULL,
    pitcher TEXT,
    team TEXT,
    opponent TEXT,
    pitcher_id INTEGER,
    line REAL,
    odds INTEGER,
    book TEXT,
    projected_k REAL,
    edge REAL,
    true_prob REAL,
    ev_pct REAL,
    units REAL,
    created_ts REAL,
    status TEXT DEFAULT 'open',
    actual_k INTEGER,
    closing_line REAL,
    result TEXT,
    profit_units REAL,
    clv REAL,
    graded_ts REAL,
    PRIMARY KEY (day, prop_id, side)
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def record_line(prop_key: str, day: str, line: float) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO line_snapshots (prop_key, day, ts, line) VALUES (?, ?, ?, ?)",
            (prop_key, day, time.time(), line),
        )


def open_and_current(prop_key: str, day: str) -> tuple[float | None, float | None]:
    """Earliest and latest recorded line for a prop on a given day."""
    with _conn() as conn:
        first = conn.execute(
            "SELECT line FROM line_snapshots WHERE prop_key=? AND day=? ORDER BY ts ASC LIMIT 1",
            (prop_key, day),
        ).fetchone()
        last = conn.execute(
            "SELECT line FROM line_snapshots WHERE prop_key=? AND day=? ORDER BY ts DESC LIMIT 1",
            (prop_key, day),
        ).fetchone()
    return (first["line"] if first else None, last["line"] if last else None)


# --- Picks (forward track record) -----------------------------------------

# Columns set when a pick is first flagged (INSERT OR IGNORE keeps the first).
_PICK_INSERT_COLS = [
    "day", "prop_id", "side", "pitcher", "team", "opponent", "pitcher_id",
    "line", "odds", "book", "projected_k", "edge", "true_prob", "ev_pct",
    "units", "created_ts", "status",
]


def record_pick(pick: dict) -> None:
    """Log a flagged recommendation once; later flags of the same pick no-op."""
    cols = ", ".join(_PICK_INSERT_COLS)
    ph = ", ".join("?" for _ in _PICK_INSERT_COLS)
    values = [pick.get(c) for c in _PICK_INSERT_COLS]
    with _conn() as conn:
        conn.execute(f"INSERT OR IGNORE INTO picks ({cols}) VALUES ({ph})", values)


def open_picks_before(day: str) -> list[sqlite3.Row]:
    """Open picks for games on days strictly before `day` (i.e. finished)."""
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM picks WHERE status='open' AND day < ? ORDER BY day", (day,)
        ).fetchall()


def grade_pick(
    day: str, prop_id: str, side: str, *,
    actual_k: int, closing_line: float | None, result: str,
    profit_units: float, clv: float | None,
) -> None:
    with _conn() as conn:
        conn.execute(
            """UPDATE picks SET status='graded', actual_k=?, closing_line=?,
                   result=?, profit_units=?, clv=?, graded_ts=?
               WHERE day=? AND prop_id=? AND side=?""",
            (actual_k, closing_line, result, profit_units, clv, time.time(),
             day, prop_id, side),
        )


def all_picks(limit: int = 200) -> list[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM picks ORDER BY day DESC, created_ts DESC LIMIT ?", (limit,)
        ).fetchall()


def graded_picks() -> list[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute("SELECT * FROM picks WHERE status='graded'").fetchall()


def counts() -> tuple[int, int]:
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
        graded = conn.execute("SELECT COUNT(*) FROM picks WHERE status='graded'").fetchone()[0]
    return total, graded


# Ensure the schema exists for every entry path (server lifespan, scripts, tests).
init_db()
