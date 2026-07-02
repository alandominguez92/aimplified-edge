import type { Projection } from "../types.ts";

// Turn the model's point estimate + confidence interval into a probability of
// clearing a given line. We treat strikeouts as approximately normal around the
// projection, recovering sigma from the reported ~90% interval (z ≈ 1.645).
// The real model will emit calibrated probabilities directly; this keeps the
// UI honest in the meantime.

function normalCdf(x: number, mean: number, sd: number): number {
  if (sd <= 0) return x >= mean ? 1 : 0;
  const z = (x - mean) / (sd * Math.SQRT2);
  return 0.5 * (1 + erf(z));
}

// Abramowitz & Stegun 7.1.26 approximation of the error function.
function erf(x: number): number {
  const s = Math.sign(x);
  const a = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * a);
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t +
      0.254829592) *
      t *
      Math.exp(-a * a);
  return s * y;
}

function sigmaFrom(proj: Projection): number {
  const halfWidth = (proj.high - proj.low) / 2;
  return Math.max(halfWidth / 1.645, 0.5);
}

/**
 * P(strikeouts > line). For a half-point line (e.g. 5.5) there's no push, so
 * P(under) = 1 - P(over).
 */
export function probOver(proj: Projection, line: number): number {
  const sd = sigmaFrom(proj);
  return 1 - normalCdf(line, proj.projectedK, sd);
}

export function probForSide(
  proj: Projection,
  line: number,
  side: "over" | "under",
): number {
  const over = probOver(proj, line);
  return side === "over" ? over : 1 - over;
}
