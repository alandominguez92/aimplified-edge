"""Python wrapper for the C++ EV/Kelly engine (backend/engine/kelly_engine.exe).

Calls the compiled binary as a subprocess (one process per batch, whitespace
protocol). If the binary is missing or non-functional, everything transparently
falls back to the pure-Python `odds_math` — so the app never depends on the
native build being present. `odds_math` is also the oracle the C++ is verified
against, so the two agree to ~1e-9.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import odds_math

EXE = Path(__file__).resolve().parent.parent.parent / "engine" / "kelly_engine.exe"
TIERS = ["pass", "quarter", "half", "full"]

_available: bool | None = None


def available() -> bool:
    """True only if the binary exists AND passes its self-test."""
    global _available
    if _available is None:
        try:
            out = subprocess.run(
                [str(EXE), "selftest"], capture_output=True, text=True, timeout=10
            )
            _available = out.stdout.strip() == "OK"
        except (OSError, subprocess.SubprocessError):
            _available = False
    return _available


def _run(mode: str, lines: list[str]) -> list[str]:
    proc = subprocess.run(
        [str(EXE), mode], input="\n".join(lines) + "\n",
        capture_output=True, text=True, timeout=15,
    )
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def _py_eval(p: float, odds: int) -> dict:
    ev = odds_math.expected_value(p, odds)
    kelly = odds_math.kelly_fraction(p, odds)
    tier = "pass"
    if ev > 0:
        tier = "full" if kelly >= 0.06 else "half" if kelly >= 0.03 else "quarter"
    return {
        "impliedProb": odds_math.implied_prob(odds),
        "decimal": odds_math.american_to_decimal(odds),
        "ev": ev,
        "kelly": kelly,
        "edge": p - odds_math.implied_prob(odds),
        "tier": tier,
        "engine": "python",
    }


def evaluate_batch(items: list[tuple[float, int]]) -> list[dict]:
    """One dict per (prob, american_odds): impliedProb, decimal, ev, kelly, edge, tier."""
    if not items:
        return []
    if not available():
        return [_py_eval(p, o) for p, o in items]

    out = _run("eval", [f"{p:.10f} {o}" for p, o in items])
    res: list[dict] = []
    for line in out:
        implied, dec, ev, kelly, edge, tier = line.split()
        res.append({
            "impliedProb": float(implied),
            "decimal": float(dec),
            "ev": float(ev),
            "kelly": float(kelly),
            "edge": float(edge),
            "tier": TIERS[int(tier)],
            "engine": "cpp",
        })
    return res


def evaluate(p: float, odds: int) -> dict:
    return evaluate_batch([(p, odds)])[0]


def parlay(
    legs: list[tuple[float, int, str]], rho: float = 0.35, nsims: int = 50000
) -> dict:
    """Combine legs (prob, odds, gameKey). Returns naive (independence) AND a
    Monte-Carlo correlation-adjusted probability/EV for same-game legs."""
    if not legs:
        return {"american": 0, "naiveProb": 1.0, "corrProb": 1.0, "naiveEv": 0.0,
                "corrEv": 0.0, "corrPairs": 0, "maxExposure": 0.0,
                "engine": "cpp" if available() else "python"}
    if available():
        proc = subprocess.run(
            [str(EXE), "parlay", str(rho), str(nsims)],
            input="\n".join(f"{p:.10f} {o} {g}" for p, o, g in legs) + "\n",
            capture_output=True, text=True, timeout=15,
        )
        american, np_, cp, nev, cev, corr, maxexp = proc.stdout.split()
        return {"american": int(american), "naiveProb": float(np_),
                "corrProb": float(cp), "naiveEv": float(nev), "corrEv": float(cev),
                "corrPairs": int(corr), "maxExposure": float(maxexp), "engine": "cpp"}
    return _py_parlay(legs)


def _py_parlay(legs: list[tuple[float, int, str]]) -> dict:
    """Fallback: naive independence only (no Monte-Carlo correlation)."""
    dec, prob = 1.0, 1.0
    for p, o, _ in legs:
        dec *= odds_math.american_to_decimal(o)
        prob *= p
    american = odds_math.decimal_to_american(dec)
    ev = odds_math.expected_value(prob, american)
    games = [g for _, _, g in legs]
    corr = sum(
        1 for i in range(len(games)) for j in range(i + 1, len(games))
        if games[i] == games[j]
    )
    return {"american": american, "naiveProb": prob, "corrProb": prob,
            "naiveEv": ev, "corrEv": ev, "corrPairs": corr,
            "maxExposure": min(0.02, ev / 2) if ev > 0 else 0.0, "engine": "python"}
