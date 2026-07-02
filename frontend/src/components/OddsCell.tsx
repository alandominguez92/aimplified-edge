import type { BookOdds, PitcherProp } from "../types.ts";
import { fmtOdds } from "../lib/format.ts";

interface Props {
  prop: PitcherProp;
  book: BookOdds;
  onPick: (prop: PitcherProp, book: BookOdds, side: "over" | "under") => void;
  isPicked: (propId: string, side: "over" | "under") => boolean;
}

/**
 * One book's over/under cell, stacked like the Unabated grid. The side the
 * model favors is tinted: mint for a value Over, red for a value Under, gray
 * when neutral. Clicking a side adds it to the parlay slip.
 */
export function OddsCell({ prop, book, onPick, isPicked }: Props) {
  const rec = prop.projection.recommendedSide;
  return (
    <div className="flex flex-col gap-0.5 tabular text-[13px]">
      <Line
        label="o"
        data={book.over}
        accent={rec === "over" ? "value" : "neutral"}
        picked={isPicked(prop.id, "over")}
        onClick={() => book.over && onPick(prop, book, "over")}
      />
      <Line
        label="u"
        data={book.under}
        accent={rec === "under" ? "risk" : "neutral"}
        picked={isPicked(prop.id, "under")}
        onClick={() => book.under && onPick(prop, book, "under")}
      />
    </div>
  );
}

function Line({
  label,
  data,
  accent,
  picked,
  onClick,
}: {
  label: string;
  data?: { line: number; odds: number };
  accent: "value" | "risk" | "neutral";
  picked: boolean;
  onClick: () => void;
}) {
  if (!data) {
    return <div className="px-2 py-1 text-center text-neutral/30">—</div>;
  }

  const tint =
    accent === "value"
      ? "text-edge"
      : accent === "risk"
        ? "text-risk"
        : "text-ink-dim";

  return (
    <button
      onClick={onClick}
      className={[
        "group flex items-center justify-between gap-2 rounded px-2 py-1 transition-colors",
        picked
          ? "bg-edge/15 ring-1 ring-edge/40"
          : "hover:bg-panel-2",
      ].join(" ")}
    >
      <span className={tint}>
        {label}
        {data.line}
      </span>
      <span className="text-ink/90">{fmtOdds(data.odds)}</span>
    </button>
  );
}
