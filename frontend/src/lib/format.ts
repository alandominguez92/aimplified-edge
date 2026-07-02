// Small display helpers shared across the table and cards.

/** American odds always carry an explicit sign: -122, +134. */
export function fmtOdds(odds: number): string {
  return odds > 0 ? `+${odds}` : `${odds}`;
}

export function fmtPct(frac: number, digits = 0): string {
  return `${(frac * 100).toFixed(digits)}%`;
}

export function fmtSignedPct(pct: number, digits = 1): string {
  const s = pct >= 0 ? "+" : "";
  return `${s}${pct.toFixed(digits)}%`;
}

export function fmtSigned(n: number, digits = 2): string {
  const s = n >= 0 ? "+" : "";
  return `${s}${n.toFixed(digits)}`;
}

/** "3:40 PM" from an ISO timestamp, in the user's local zone. */
export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "6/26" short date. */
export function fmtDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
