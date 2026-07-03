import { useMemo, useState } from "react";
import type { Book, BookOdds, Market, PitcherProp } from "../types.ts";
import { marketLabels } from "../lib/market.ts";
import { evalProp } from "../lib/ev.ts";
import { PropRow, GRID } from "./PropRow.tsx";

const BOOKS: Book[] = ["FanDuel", "DraftKings", "Caesars", "ESPN BET"];

type SortKey = "time" | "ev" | "edge" | "line" | "sharp";

interface Props {
  props: PitcherProp[];
  market: Market;
  selectedId?: string;
  onSelect: (p: PitcherProp) => void;
  onPick: (prop: PitcherProp, book: BookOdds, side: "over" | "under") => void;
  isPicked: (propId: string, side: "over" | "under") => boolean;
}

export function PropTable({ props, market, selectedId, onSelect, onPick, isPicked }: Props) {
  const [sort, setSort] = useState<SortKey>("time");
  const [query, setQuery] = useState("");

  const sorted = useMemo(() => {
    const copy = [...props];
    if (sort === "ev") {
      // highest EV first; plays with no recommendation sink to the bottom
      const ev = new Map(
        props.map((p) => [p.id, evalProp(p)?.evPct ?? -Infinity]),
      );
      copy.sort((a, b) => ev.get(b.id)! - ev.get(a.id)!);
      return copy;
    }
    copy.sort((a, b) => {
      switch (sort) {
        case "edge":
          return Math.abs(b.projection.edge) - Math.abs(a.projection.edge);
        case "line":
          return b.marketLine - a.marketLine;
        case "sharp":
          return b.sharp.strength - a.sharp.strength;
        case "time":
        default:
          return a.gameTime.localeCompare(b.gameTime);
      }
    });
    return copy;
  }, [props, sort]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter(
      (p) =>
        p.pitcher.toLowerCase().includes(q) ||
        p.team.toLowerCase().includes(q) ||
        p.opponent.toLowerCase().includes(q),
    );
  }, [sorted, query]);

  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-panel/40">
      {/* search */}
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <span className="text-neutral" aria-hidden>🔍</span>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${marketLabels(market).player.toLowerCase()} or team…`}
          className="w-full bg-transparent text-[13px] text-ink placeholder:text-neutral/60 focus:outline-none"
        />
        {query && (
          <button
            onClick={() => setQuery("")}
            className="rounded px-1.5 text-[11px] text-neutral hover:text-ink"
            aria-label="Clear search"
          >
            ✕
          </button>
        )}
      </div>

      {/* sort toolbar */}
      <div className="flex items-center gap-2 border-b border-line px-3 py-2 text-[11px] text-ink-dim">
        <span className="uppercase tracking-wide text-neutral">Sort</span>
        {(
          [
            ["time", "Game time"],
            ["ev", "EV"],
            ["edge", "Projection edge"],
            ["line", "Line value"],
            ["sharp", "Sharp signal"],
          ] as [SortKey, string][]
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setSort(k)}
            className={[
              "rounded px-2 py-0.5 transition-colors",
              sort === k ? "bg-edge/15 text-edge" : "hover:bg-panel-2 hover:text-ink",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
        <span className="ml-auto tabular text-neutral">
          {filtered.length}
          {query && `/${sorted.length}`}{" "}
          {market === "hits" ? "batters" : "starters"}
        </span>
      </div>

      {/* column header */}
      <div
        className={`${GRID} sticky top-14 z-20 items-center border-b border-line bg-panel px-2 py-2 text-[10px] uppercase tracking-wide text-neutral`}
      >
        <div className="pl-1">Time</div>
        <div>{marketLabels(market).player}</div>
        <div className="text-center">Edge</div>
        <div className="text-center">EV</div>
        {BOOKS.map((b) => (
          <div key={b} className="px-1 text-center">
            {b}
          </div>
        ))}
      </div>

      {/* rows */}
      <div>
        {filtered.map((p) => (
          <PropRow
            key={p.id}
            prop={p}
            selected={p.id === selectedId}
            onSelect={onSelect}
            onPick={onPick}
            isPicked={isPicked}
          />
        ))}
        {filtered.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-ink-dim">
            {query
              ? `No ${marketLabels(market).player.toLowerCase()}s match “${query}”.`
              : "No active games right now — finished games drop off the board."}
          </div>
        )}
      </div>
    </div>
  );
}
