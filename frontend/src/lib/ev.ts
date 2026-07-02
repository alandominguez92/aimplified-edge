import type { PitcherProp } from "../types.ts";
import { americanToDecimal, expectedValue } from "./odds.ts";
import { probForSide } from "./projection.ts";

export interface RowEv {
  side: "over" | "under";
  line: number;
  odds: number;
  book: string;
  trueProb: number;
  evPct: number;
}

/** Best (most bettor-favorable) price for a side across all books. */
export function bestPrice(prop: PitcherProp, side: "over" | "under") {
  let best: { line: number; odds: number; book: string } | null = null;
  for (const b of prop.books) {
    const s = b[side];
    if (!s) continue;
    if (!best || americanToDecimal(s.odds) > americanToDecimal(best.odds)) {
      best = { line: s.line, odds: s.odds, book: b.book };
    }
  }
  return best;
}

/**
 * EV for the model's recommended side at the best available price. Null when
 * there's no recommendation or no market. This is the honest value gate: a big
 * projection edge can still be −EV once the juice is paid.
 */
export function evalProp(prop: PitcherProp): RowEv | null {
  const side = prop.projection.recommendedSide;
  if (!side) return null;
  const bp = bestPrice(prop, side);
  if (!bp) return null;
  const trueProb = probForSide(prop.projection, bp.line, side);
  return {
    side,
    line: bp.line,
    odds: bp.odds,
    book: bp.book,
    trueProb,
    evPct: expectedValue(trueProb, bp.odds) * 100,
  };
}
