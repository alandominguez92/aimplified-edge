import type { Market, PitcherProp } from "../types.ts";
import { americanToDecimal, evaluate, type KellyTier } from "../lib/odds.ts";
import { marketLabels } from "../lib/market.ts";
import { probForSide } from "../lib/projection.ts";
import { fmtOdds, fmtPct, fmtSigned, fmtSignedPct } from "../lib/format.ts";

/** Best (most bettor-favorable) price for a side across all books. */
function bestPrice(prop: PitcherProp, side: "over" | "under") {
  let best: { book: string; line: number; odds: number } | null = null;
  for (const b of prop.books) {
    const s = b[side];
    if (!s) continue;
    if (!best || americanToDecimal(s.odds) > americanToDecimal(best.odds)) {
      best = { book: b.book, line: s.line, odds: s.odds };
    }
  }
  return best;
}

const TIER_LABEL: Record<KellyTier, string> = {
  full: "Full Kelly",
  half: "Half Kelly",
  quarter: "Quarter Kelly",
  pass: "Pass",
};

export function PredictionCard({
  prop,
  market = "strikeouts",
}: {
  prop: PitcherProp | null;
  market?: Market;
}) {
  const labels = marketLabels(market);
  if (!prop) {
    return (
      <div className="rounded-lg border border-line bg-panel/40 p-6 text-center text-sm text-ink-dim">
        Select a {labels.player.toLowerCase()} to see the model card.
      </div>
    );
  }

  const { projection: proj, sharp } = prop;
  const side = proj.recommendedSide;
  const price = side ? bestPrice(prop, side) : null;
  const trueProb = side && price ? probForSide(proj, price.line, side) : 0;
  const ev = side && price ? evaluate(trueProb, price.odds) : null;

  return (
    <div className="rounded-lg border border-line bg-panel/40">
      <div className="border-b border-line px-4 py-3">
        <div className="text-sm font-semibold text-ink">{prop.pitcher}</div>
        <div className="text-[11px] text-ink-dim">
          {prop.team} {prop.isHome ? "vs." : "@"} {prop.opponent} · {labels.propNoun}
        </div>
      </div>

      {/* projection headline */}
      <div className="grid grid-cols-2 gap-px bg-line">
        <Stat label={labels.projected} value={proj.projectedK.toFixed(1)} accent />
        <Stat
          label="Market line"
          value={prop.marketLine.toFixed(1)}
        />
        <Stat
          label="Edge"
          value={fmtSigned(proj.edge, 1)}
          tone={Math.abs(proj.edge) >= 0.75 ? (proj.edge > 0 ? "value" : "risk") : undefined}
        />
        <Stat label="Confidence" value={fmtPct(proj.confidence)} />
      </div>

      {/* CI bar */}
      <div className="px-4 py-3">
        <div className="mb-1 flex justify-between text-[10px] text-neutral tabular">
          <span>{proj.low.toFixed(1)}</span>
          <span>90% interval</span>
          <span>{proj.high.toFixed(1)}</span>
        </div>
        <ConfidenceBar proj={proj} line={prop.marketLine} />
      </div>

      {/* recommendation */}
      <div className="border-t border-line px-4 py-3">
        {side && price && ev ? (
          <>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-wide text-neutral">
                Recommendation
              </span>
              <span
                className={`rounded px-2 py-0.5 text-xs font-semibold ${
                  side === "over"
                    ? "bg-edge/15 text-edge"
                    : "bg-risk/15 text-risk"
                }`}
              >
                {side.toUpperCase()} {price.line} · {fmtOdds(price.odds)} ({price.book})
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <Mini label="True %" value={fmtPct(ev.trueProb)} />
              <Mini
                label="EV"
                value={fmtSignedPct(ev.evPct)}
                tone={ev.evPct > 0 ? "value" : "risk"}
              />
              <Mini
                label="Size"
                value={ev.tier === "pass" ? "—" : `${ev.units.toFixed(1)}u`}
              />
            </div>
            <div className="mt-2 flex items-center justify-between text-[11px]">
              <span className="text-ink-dim">
                Sizing: <span className="text-ink">{TIER_LABEL[ev.tier]}</span>
              </span>
              <span className="text-ink-dim">
                vs implied {fmtPct(ev.impliedProb)}
              </span>
            </div>
          </>
        ) : (
          <div className="text-center text-sm text-ink-dim">
            No actionable edge — model agrees with the market.
          </div>
        )}
      </div>

      {/* sharp signal */}
      {sharp.side && sharp.strength > 0.6 && (
        <div className="flex items-center gap-2 border-t border-line bg-edge/5 px-4 py-2.5 text-[11px]">
          <span className="relative flex h-3 w-3">
            <span className="radar-ping absolute inline-flex h-full w-full rounded-full bg-edge/60" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-edge/80" />
          </span>
          <span className="text-ink-dim">
            <span className="font-semibold text-edge">Sharp money</span> on the{" "}
            {sharp.side.toUpperCase()} — {Math.round(sharp.strength * 100)}% signal,{" "}
            {sharp.ticketPct}% public tickets Over
          </span>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
  tone,
}: {
  label: string;
  value: string;
  accent?: boolean;
  tone?: "value" | "risk";
}) {
  const color =
    tone === "value" ? "text-edge" : tone === "risk" ? "text-risk" : accent ? "text-edge" : "text-ink";
  return (
    <div className="bg-panel px-4 py-3">
      <div className="text-[10px] uppercase tracking-wide text-neutral">{label}</div>
      <div className={`tabular text-xl font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function Mini({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "value" | "risk";
}) {
  const color = tone === "value" ? "text-edge" : tone === "risk" ? "text-risk" : "text-ink";
  return (
    <div className="rounded bg-panel px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-neutral">{label}</div>
      <div className={`tabular text-sm font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function ConfidenceBar({
  proj,
  line,
}: {
  proj: PitcherProp["projection"];
  line: number;
}) {
  // Scale a small window around the interval for visual placement.
  const lo = Math.min(proj.low, line) - 0.5;
  const hi = Math.max(proj.high, line) + 0.5;
  const span = hi - lo || 1;
  const pct = (v: number) => ((v - lo) / span) * 100;

  return (
    <div className="relative h-3 rounded-full bg-panel-2">
      <div
        className="absolute top-0 h-3 rounded-full bg-edge/25"
        style={{ left: `${pct(proj.low)}%`, width: `${pct(proj.high) - pct(proj.low)}%` }}
      />
      {/* projection marker */}
      <div
        className="absolute top-[-2px] h-[18px] w-[3px] -translate-x-1/2 rounded bg-edge"
        style={{ left: `${pct(proj.projectedK)}%` }}
        title={`Projected ${proj.projectedK.toFixed(1)}`}
      />
      {/* market line marker */}
      <div
        className="absolute top-[-2px] h-[18px] w-[3px] -translate-x-1/2 rounded bg-ink/70"
        style={{ left: `${pct(line)}%` }}
        title={`Line ${line.toFixed(1)}`}
      />
    </div>
  );
}
