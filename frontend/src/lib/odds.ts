// EV / Kelly / implied-probability math.
//
// This is the TypeScript reference implementation. The same formulas will live
// in the C++ engine (kelly.cpp) once the backend lands; keeping a browser-side
// copy lets the UI show live EV/Kelly without a round-trip and gives us an
// oracle to test the C++ port against.

/** American odds -> decimal payout multiplier (e.g. -120 -> 1.833, +130 -> 2.30). */
export function americanToDecimal(american: number): number {
  return american > 0 ? 1 + american / 100 : 1 + 100 / Math.abs(american);
}

/** Implied probability from American odds, INCLUDING the book's vig. */
export function impliedProb(american: number): number {
  return american > 0
    ? 100 / (american + 100)
    : Math.abs(american) / (Math.abs(american) + 100);
}

/**
 * Remove the vig from a two-way market to get the book's "fair" probability
 * for the first side. Normalizes the two implied probs so they sum to 1.
 */
export function novig(oddsA: number, oddsB: number): number {
  const a = impliedProb(oddsA);
  const b = impliedProb(oddsB);
  return a / (a + b);
}

/**
 * Expected value per 1 unit staked, given our true win probability `p` and the
 * American `odds` offered. Returns a fraction: 0.05 == +5% EV.
 */
export function expectedValue(p: number, odds: number): number {
  const dec = americanToDecimal(odds);
  return p * (dec - 1) - (1 - p);
}

/**
 * Kelly fraction of bankroll to stake. `b` is net decimal odds (payout - 1).
 * Clamped at 0 (never recommend betting -EV). Returns full-Kelly fraction.
 */
export function kellyFraction(p: number, odds: number): number {
  const b = americanToDecimal(odds) - 1;
  if (b <= 0) return 0;
  const f = (p * b - (1 - p)) / b;
  return Math.max(0, f);
}

export type KellyTier = "full" | "half" | "quarter" | "pass";

export interface EvResult {
  impliedProb: number; // with vig
  trueProb: number; // our model probability
  evPct: number; // +EV in percent
  kelly: number; // full-kelly fraction of bankroll
  units: number; // suggested units at quarter-Kelly, capped
  tier: KellyTier;
}

/**
 * Bundle the numbers the PredictionCard needs. We bet conservatively:
 * sizing is reported at quarter-Kelly and capped at 3u, and we map the raw
 * edge to a coarse tier the UI can badge.
 */
export function evaluate(trueProb: number, odds: number): EvResult {
  const ev = expectedValue(trueProb, odds);
  const kelly = kellyFraction(trueProb, odds);
  const quarter = kelly / 4;
  const units = Math.min(3, Math.round(quarter * 100) / 10); // ~units on a 10u bankroll

  let tier: KellyTier = "pass";
  if (ev > 0) {
    if (kelly >= 0.06) tier = "full";
    else if (kelly >= 0.03) tier = "half";
    else tier = "quarter";
  }

  return {
    impliedProb: impliedProb(odds),
    trueProb,
    evPct: ev * 100,
    kelly,
    units,
    tier,
  };
}
