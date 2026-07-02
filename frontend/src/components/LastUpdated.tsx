import { useEffect, useState } from "react";

/**
 * "updated 12s ago" — ticks on its own 1s timer so the rest of the app doesn't
 * re-render every second. Includes a manual refresh button.
 */
export function LastUpdated({
  at,
  refreshing,
  onRefresh,
}: {
  at: number | null;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const ago = at ? Math.max(0, Math.round((Date.now() - at) / 1000)) : null;
  const label =
    ago === null ? "—" : ago < 5 ? "just now" : ago < 60 ? `${ago}s ago` : `${Math.floor(ago / 60)}m ago`;

  return (
    <span className="flex items-center gap-2 text-[11px] text-ink-dim">
      <span className="tabular">
        {refreshing ? "refreshing…" : `updated ${label}`}
      </span>
      <button
        onClick={onRefresh}
        disabled={refreshing}
        title="Refresh now"
        className="rounded border border-line px-1.5 py-0.5 text-ink-dim transition-colors hover:border-edge/40 hover:text-edge disabled:opacity-50"
      >
        ↻
      </button>
    </span>
  );
}
