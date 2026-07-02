import { useEffect, useState } from "react";
import type { ParlayEval, ParlayPick } from "../types.ts";
import { getParlay } from "../data/slate.ts";
import { americanToDecimal, expectedValue } from "../lib/odds.ts";
import { fmtOdds, fmtPct, fmtSignedPct } from "../lib/format.ts";

interface Props {
  picks: ParlayPick[];
  onRemove: (propId: string, side: "over" | "under") => void;
  onClear: () => void;
}

/** Decimal odds -> American, for displaying the combined parlay price. */
function decimalToAmerican(dec: number): number {
  const b = dec - 1;
  return b >= 1 ? Math.round(b * 100) : Math.round(-100 / b);
}

export function ParlaySlip({ picks, onRemove, onClear }: Props) {
  // Pairs of legs from the same game are positively correlated (same game
  // script drives both strikeout totals), which inflates true parlay odds.
  const correlated = new Set<string>();
  for (let i = 0; i < picks.length; i++) {
    for (let j = i + 1; j < picks.length; j++) {
      if (
        picks[i].gameKey === picks[j].gameKey ||
        picks[i].propId === picks[j].propId
      ) {
        correlated.add(picks[i].propId + picks[i].side);
        correlated.add(picks[j].propId + picks[j].side);
      }
    }
  }

  const combinedDec = picks.reduce(
    (acc, p) => acc * americanToDecimal(p.odds),
    1,
  );
  // Naive independence assumption — flagged when correlation is present.
  const combinedProb = picks.reduce((acc, p) => acc * p.trueProb, 1);
  const combinedAmerican = decimalToAmerican(combinedDec);
  const ev = picks.length ? expectedValue(combinedProb, combinedAmerican) : 0;
  // Conservative cap: never risk more than 2% of bankroll on a parlay.
  const maxExposure = Math.max(0, Math.min(0.02, ev > 0 ? ev / 2 : 0));

  // Correlation-adjusted numbers from the C++ Monte-Carlo engine (via /api/parlay).
  const [cpp, setCpp] = useState<ParlayEval | null>(null);
  const key = picks.map((p) => `${p.propId}${p.side}${p.odds}`).join("|");
  useEffect(() => {
    if (picks.length < 2) {
      setCpp(null);
      return;
    }
    let alive = true;
    getParlay(
      picks.map((p) => ({ prob: p.trueProb, odds: p.odds, gameKey: p.gameKey })),
    ).then((r) => alive && setCpp(r));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const showCorr = cpp && cpp.corrPairs > 0;

  return (
    <div className="flex h-full flex-col rounded-lg border border-line bg-panel/40">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <span className="text-sm font-semibold text-ink">
          Parlay slip{" "}
          <span className="tabular text-ink-dim">({picks.length})</span>
        </span>
        {picks.length > 0 && (
          <button
            onClick={onClear}
            className="text-[11px] text-ink-dim hover:text-risk"
          >
            Clear
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {picks.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-ink-dim">
            Click any odds cell to add a leg.
          </div>
        ) : (
          picks.map((p) => {
            const corr = correlated.has(p.propId + p.side);
            return (
              <div
                key={p.propId + p.side}
                className="flex items-start gap-2 border-b border-line/60 px-4 py-2.5"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm text-ink">{p.pitcher}</span>
                    {corr && (
                      <span
                        title="Correlated with another leg in the same game — true odds are lower than shown"
                        className="rounded bg-risk/15 px-1 text-[9px] font-semibold text-risk"
                      >
                        CORR
                      </span>
                    )}
                  </div>
                  <div className="tabular text-[11px] text-ink-dim">
                    {p.side.toUpperCase()} {p.line} · {fmtOdds(p.odds)} · {p.book}
                  </div>
                </div>
                <button
                  onClick={() => onRemove(p.propId, p.side)}
                  className="text-ink-dim hover:text-risk"
                  aria-label="Remove leg"
                >
                  ✕
                </button>
              </div>
            );
          })
        )}
      </div>

      {picks.length > 0 && (
        <div className="border-t border-line px-4 py-3 text-[12px]">
          {correlated.size > 0 && (
            <div className="mb-2 rounded border border-risk/30 bg-risk/10 px-2 py-1.5 text-[11px] text-risk">
              ⚠ Correlated legs (same game). Independence understates the true
              win %; the correlation-adjusted line below is the honest estimate.
            </div>
          )}
          <Row label="Combined odds" value={fmtOdds(combinedAmerican)} />
          <Row
            label={showCorr ? "Win % (independent)" : "Model win %"}
            value={fmtPct(combinedProb, 1)}
          />
          <Row
            label="Combined EV"
            value={fmtSignedPct(ev * 100)}
            tone={ev > 0 ? "value" : "risk"}
          />

          {showCorr && cpp && (
            <div className="mt-2 border-t border-line pt-2">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-neutral">
                Correlation-adjusted
                <span className="rounded bg-edge/15 px-1 text-[9px] font-semibold text-edge">
                  C++ MC
                </span>
              </div>
              <Row label="True win %" value={fmtPct(cpp.corrProb, 1)} tone="value" />
              <Row
                label="True EV"
                value={fmtSignedPct(cpp.corrEv * 100)}
                tone={cpp.corrEv > 0 ? "value" : "risk"}
              />
            </div>
          )}

          <Row
            label="Max exposure"
            value={`${((showCorr && cpp ? cpp.maxExposure : maxExposure) * 100).toFixed(1)}% bankroll`}
          />
        </div>
      )}
    </div>
  );
}

function Row({
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
    <div className="flex items-center justify-between py-0.5">
      <span className="text-ink-dim">{label}</span>
      <span className={`tabular font-semibold ${color}`}>{value}</span>
    </div>
  );
}
