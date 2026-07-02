import type { SharpSignal } from "../types.ts";

/**
 * The ⚡ sharp-money indicator. Shown only when sharp action is detected
 * (strength > 0.6). The tooltip explains the read: ticket % vs. line move.
 */
export function SharpSignalBadge({ sharp }: { sharp: SharpSignal }) {
  if (!sharp.side || sharp.strength <= 0.6) return null;

  const moved = sharp.currentLine !== sharp.openLine;
  const dir = sharp.currentLine > sharp.openLine ? "up" : "down";
  const tip = [
    `Sharp action on the ${sharp.side.toUpperCase()} (${Math.round(sharp.strength * 100)}%)`,
    `${sharp.ticketPct}% of tickets on the Over`,
    moved
      ? `Line moved ${dir} ${sharp.openLine} → ${sharp.currentLine} against the public`
      : `Line steady at ${sharp.currentLine} despite lopsided tickets`,
  ].join(" · ");

  return (
    <span
      title={tip}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold text-edge bg-edge/10 border border-edge/25 cursor-help"
    >
      <span aria-hidden>⚡</span>
      {sharp.side === "over" ? "O" : "U"}
    </span>
  );
}
