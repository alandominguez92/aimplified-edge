import type { TrackRecord as Record } from "../types.ts";

/**
 * Forward track record. Picks are logged when flagged and graded once games go
 * final, so early on this shows a "building" state — the numbers become
 * meaningful as a real sample accrues. This is the honest ROI/CLV ledger, not a
 * backtest against odds we never had.
 */
export function TrackRecord({ record }: { record: Record | null }) {
  return (
    <div className="rounded-lg border border-line bg-panel/40">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <span className="text-sm font-semibold text-ink">Track record</span>
        <span className="text-[10px] uppercase tracking-wide text-neutral">
          live · flat 1u
        </span>
      </div>

      {!record || record.gradedPicks === 0 ? (
        <div className="px-4 py-4 text-[12px] text-ink-dim">
          Building record — recommendations are logged when flagged and graded
          after games finish.
          <div className="mt-2 flex gap-4 tabular text-ink">
            <span>
              <span className="text-edge">{record?.openPicks ?? 0}</span> open
            </span>
            <span>
              <span className="text-neutral">{record?.gradedPicks ?? 0}</span> graded
            </span>
          </div>
        </div>
      ) : (
        <div className="px-4 py-3">
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Stat label="Record" value={record.record} />
            <Stat
              label="ROI"
              value={record.roiPct === null ? "—" : `${record.roiPct > 0 ? "+" : ""}${record.roiPct}%`}
              tone={record.roiPct !== null ? (record.roiPct >= 0 ? "value" : "risk") : undefined}
            />
            <Stat
              label="Units"
              value={`${record.unitsProfit > 0 ? "+" : ""}${record.unitsProfit.toFixed(2)}u`}
              tone={record.unitsProfit >= 0 ? "value" : "risk"}
            />
            <Stat
              label="Hit rate"
              value={record.hitRate === null ? "—" : `${(record.hitRate * 100).toFixed(0)}%`}
            />
            <Stat
              label="Avg CLV"
              value={record.avgClv === null ? "—" : `${record.avgClv > 0 ? "+" : ""}${record.avgClv}`}
              tone={record.avgClv !== null ? (record.avgClv >= 0 ? "value" : "risk") : undefined}
            />
            <Stat label="Graded" value={`${record.gradedPicks}`} />
          </div>
          <div className="mt-3 border-t border-line pt-2 text-[10px] text-neutral">
            {record.openPicks} open · flat 1u staking · CLV in K (＋ = line moved your way)
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({
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
    <div>
      <div className="text-[10px] uppercase tracking-wide text-neutral">{label}</div>
      <div className={`tabular text-base font-semibold ${color}`}>{value}</div>
    </div>
  );
}
