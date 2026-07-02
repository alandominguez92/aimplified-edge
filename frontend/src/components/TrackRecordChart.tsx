import type { PickHistoryPoint } from "../types.ts";

/**
 * Cumulative-units performance chart over graded picks (flat 1u). Pure SVG, no
 * chart lib. Renders nothing until at least one pick has been graded — so it
 * appears automatically once the daily job settles some games.
 */
export function TrackRecordChart({ history }: { history: PickHistoryPoint[] }) {
  if (history.length === 0) return null;

  const W = 720;
  const H = 220;
  const padL = 40;
  const padR = 16;
  const padT = 16;
  const padB = 28;

  // Prepend a 0-unit origin so the line starts at the bankroll baseline.
  const units = [0, ...history.map((h) => h.cumulativeUnits)];
  const n = units.length;
  const yMax = Math.max(0.5, ...units);
  const yMin = Math.min(0, ...units);
  const range = yMax - yMin || 1;

  const x = (i: number) => padL + (i * (W - padL - padR)) / Math.max(1, n - 1);
  const y = (u: number) => padT + ((yMax - u) / range) * (H - padT - padB);

  const line = units.map((u, i) => `${x(i)},${y(u)}`).join(" ");
  const area = `${padL},${y(0)} ${line} ${x(n - 1)},${y(0)}`;

  const final = history[history.length - 1].cumulativeUnits;
  const wins = history.filter((h) => h.result === "win").length;
  const losses = history.filter((h) => h.result === "loss").length;
  const pushes = history.filter((h) => h.result === "push").length;
  const clvs = history.map((h) => h.clv).filter((c): c is number => c !== null);
  const avgClv = clvs.length ? clvs.reduce((a, b) => a + b, 0) / clvs.length : null;
  const up = final >= 0;
  const stroke = up ? "var(--color-edge)" : "var(--color-risk)";

  return (
    <div className="rounded-lg border border-line bg-panel/40">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-3">
        <span className="text-sm font-semibold text-ink">Performance</span>
        <div className="flex items-baseline gap-4 text-[12px]">
          <span className="text-ink-dim">
            {history.length} graded · {wins}-{losses}
            {pushes ? `-${pushes}` : ""}
          </span>
          {avgClv !== null && (
            <span className="text-ink-dim">
              CLV{" "}
              <span className={`tabular ${avgClv >= 0 ? "text-edge" : "text-risk"}`}>
                {avgClv >= 0 ? "+" : ""}
                {avgClv.toFixed(2)}
              </span>
            </span>
          )}
          <span className={`tabular text-base font-semibold ${up ? "text-edge" : "text-risk"}`}>
            {up ? "+" : ""}
            {final.toFixed(2)}u
          </span>
        </div>
      </div>

      <div className="px-2 py-2">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Cumulative units">
          <defs>
            <linearGradient id="perfFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
              <stop offset="100%" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* zero baseline */}
          <line
            x1={padL} y1={y(0)} x2={W - padR} y2={y(0)}
            stroke="var(--color-line)" strokeWidth="1" strokeDasharray="3 3"
          />
          <text x={padL - 6} y={y(0) + 3} textAnchor="end" fontSize="10" fill="var(--color-neutral)">0</text>
          <text x={padL - 6} y={y(yMax) + 3} textAnchor="end" fontSize="10" fill="var(--color-neutral)">
            {yMax.toFixed(1)}
          </text>
          {yMin < 0 && (
            <text x={padL - 6} y={y(yMin) + 3} textAnchor="end" fontSize="10" fill="var(--color-neutral)">
              {yMin.toFixed(1)}
            </text>
          )}

          <polygon points={area} fill="url(#perfFill)" />
          <polyline points={line} fill="none" stroke={stroke} strokeWidth="2"
            strokeLinejoin="round" strokeLinecap="round" />
          <circle cx={x(n - 1)} cy={y(final)} r="3.5" fill={stroke} />
        </svg>
      </div>

      <div className="border-t border-line px-4 py-2 text-[10px] text-neutral">
        cumulative units at flat 1u · settles as games finish
      </div>
    </div>
  );
}
