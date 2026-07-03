import type { Book, BookOdds, PitcherProp } from "../types.ts";
import { fmtTime, fmtSigned, fmtOdds, fmtSignedPct } from "../lib/format.ts";
import { evalProp } from "../lib/ev.ts";
import { OddsCell } from "./OddsCell.tsx";
import { SharpSignalBadge } from "./SharpSignalBadge.tsx";

const BOOKS: Book[] = ["FanDuel", "DraftKings", "Caesars", "ESPN BET"];
const EMPTY: BookOdds = { book: "FanDuel" };

export const GRID =
  "grid grid-cols-[64px_minmax(200px,1.3fr)_72px_92px_repeat(4,minmax(88px,1fr))]";

interface Props {
  prop: PitcherProp;
  selected: boolean;
  onSelect: (p: PitcherProp) => void;
  onPick: (prop: PitcherProp, book: BookOdds, side: "over" | "under") => void;
  isPicked: (propId: string, side: "over" | "under") => boolean;
}

export function PropRow({ prop, selected, onSelect, onPick, isPicked }: Props) {
  const sharpOn = !!prop.sharp.side && prop.sharp.strength > 0.6;
  const edge = prop.projection.edge;

  return (
    <div
      onClick={() => onSelect(prop)}
      className={[
        GRID,
        "group relative items-center border-b border-line/70 px-2 cursor-pointer",
        selected ? "bg-panel-2" : "hover:bg-panel/60",
        sharpOn ? "sharp-row" : "",
      ].join(" ")}
    >
      {/* time */}
      <div className="py-2 pl-1 text-[11px] leading-tight text-ink-dim tabular">
        {fmtTime(prop.gameTime)}
      </div>

      {/* pitcher + matchup */}
      <div className="flex items-center gap-2 py-2 pr-2">
        <Avatar name={prop.pitcher} />
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-sm font-medium text-ink">
              {prop.pitcher}
            </span>
            {prop.market !== "hits" && (
              <span className="text-[10px] text-neutral">(P)</span>
            )}
            {prop.market === "hits" && prop.l10Avg != null && (
              <HotBadge avg={prop.l10Avg} line={prop.l10Line} />
            )}
            <SharpSignalBadge sharp={prop.sharp} />
          </div>
          <div className="text-[11px] text-ink-dim">
            <span className="font-semibold text-ink/80">{prop.team}</span>{" "}
            {prop.isHome ? "vs." : "@"}{" "}
            <span className="font-semibold text-ink/80">{prop.opponent}</span>
          </div>
        </div>

        {/* hover mini stat card (pitcher last-5; batters have no last-5 data) */}
        {prop.projection.last5K.length > 0 && <MiniCard prop={prop} />}
      </div>

      {/* model edge */}
      <div className="py-2 text-center">
        <EdgePill edge={edge} />
      </div>

      {/* best-price EV for the recommended side */}
      <div className="py-2 text-center">
        <EvCell prop={prop} />
      </div>

      {/* book odds */}
      {BOOKS.map((b) => {
        const book = prop.books.find((x) => x.book === b) ?? { ...EMPTY, book: b };
        return (
          <div key={b} className="px-1 py-1.5" onClick={(e) => e.stopPropagation()}>
            <OddsCell prop={prop} book={book} onPick={onPick} isPicked={isPicked} />
          </div>
        );
      })}
    </div>
  );
}

function EdgePill({ edge }: { edge: number }) {
  const strong = Math.abs(edge) >= 0.75;
  const cls = !strong
    ? "text-neutral bg-panel-2"
    : edge > 0
      ? "text-edge bg-edge/10 border border-edge/25"
      : "text-risk bg-risk/10 border border-risk/25";
  return (
    <span
      title={strong ? "Model disagrees with market by >0.75 K" : "Within market range"}
      className={`tabular inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold ${cls}`}
    >
      {fmtSigned(edge, 1)}
    </span>
  );
}

function EvCell({ prop }: { prop: PitcherProp }) {
  const ev = evalProp(prop);
  if (!ev) return <span className="text-[11px] text-neutral/40">—</span>;
  const good = ev.evPct >= 0;
  return (
    <span
      title={`${ev.side.toUpperCase()} ${ev.line} · ${fmtOdds(ev.odds)} (${ev.book}) · true ${(ev.trueProb * 100).toFixed(0)}%`}
      className="inline-flex flex-col items-center leading-tight cursor-help"
    >
      <span
        className={`tabular text-[12px] font-semibold ${good ? "text-edge" : "text-risk"}`}
      >
        {fmtSignedPct(ev.evPct, 0)}
      </span>
      <span className="tabular text-[10px] text-ink-dim">{fmtOdds(ev.odds)}</span>
    </span>
  );
}

function HotBadge({ avg, line }: { avg: number; line?: string | null }) {
  // baseball AVG convention: ".471", no leading zero
  const shown = avg.toFixed(3).replace(/^0/, "");
  return (
    <span
      title={`Hot: ${line ?? ""} over the last 10 days (${shown} AVG)`.trim()}
      className="tabular inline-flex items-center gap-0.5 rounded bg-edge/10 px-1 py-0.5 text-[9px] font-semibold text-edge ring-1 ring-edge/25 cursor-help"
    >
      🔥 L10 {shown}
    </span>
  );
}

function Avatar({ name }: { name: string }) {
  const initials = name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("");
  return (
    <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-panel-2 text-[10px] font-semibold text-ink-dim ring-1 ring-line">
      {initials}
    </div>
  );
}

function MiniCard({ prop }: { prop: PitcherProp }) {
  const { last5K, parkFactor, weather } = prop.projection;
  const icon = { clear: "☀", cloudy: "☁", rain: "🌧", dome: "⌂" }[weather.condition];
  const max = Math.max(...last5K, 1);
  return (
    <div className="pointer-events-none absolute left-16 top-full z-40 mt-1 hidden w-56 rounded-lg border border-line bg-panel p-3 shadow-2xl shadow-black/60 group-hover:block">
      <div className="mb-2 text-[10px] uppercase tracking-wide text-neutral">
        Last 5 starts — K
      </div>
      <div className="mb-3 flex items-end gap-1.5 h-12">
        {last5K.map((k, i) => (
          <div key={i} className="flex flex-1 flex-col items-center gap-1">
            <div
              className="w-full rounded-sm bg-edge/70"
              style={{ height: `${(k / max) * 100}%` }}
            />
            <span className="tabular text-[9px] text-ink-dim">{k}</span>
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[11px] text-ink-dim">
        <span>
          Park <span className="tabular text-ink">{parkFactor.toFixed(2)}</span>
        </span>
        <span>
          {icon} <span className="tabular text-ink">{weather.tempF}°</span>
        </span>
      </div>
    </div>
  );
}
