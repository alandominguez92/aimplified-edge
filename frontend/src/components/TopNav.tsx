import type { Sport } from "../types.ts";

const SPORTS: { id: Sport; live: boolean }[] = [
  { id: "MLB", live: true },
  { id: "NBA", live: false },
  { id: "NHL", live: false },
  { id: "NFL", live: false },
  { id: "Soccer", live: false },
];

interface Props {
  sport: Sport;
  onSport: (s: Sport) => void;
}

export function TopNav({ sport, onSport }: Props) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-base/95 backdrop-blur">
      <div className="flex items-center gap-6 px-5 h-14">
        <div className="flex items-center gap-2 shrink-0">
          <Logo />
          <span className="font-semibold tracking-tight text-ink">
            Aimplified<span className="text-edge">Edge</span>
          </span>
        </div>

        <nav className="flex items-center gap-1">
          {SPORTS.map((s) => {
            const active = s.id === sport;
            return (
              <button
                key={s.id}
                onClick={() => s.live && onSport(s.id)}
                disabled={!s.live}
                className={[
                  "relative px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                  active
                    ? "bg-panel-2 text-edge"
                    : s.live
                      ? "text-ink-dim hover:text-ink hover:bg-panel"
                      : "text-neutral/40 cursor-not-allowed",
                ].join(" ")}
              >
                {s.id}
                {!s.live && (
                  <span className="ml-1 text-[9px] uppercase text-neutral/40">
                    soon
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-3 text-xs text-ink-dim">
          <span className="flex items-center gap-1.5">
            <span className="relative flex h-2 w-2">
              <span className="radar-ping absolute inline-flex h-full w-full rounded-full bg-edge/60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-edge" />
            </span>
            live odds
          </span>
        </div>
      </div>
    </header>
  );
}

function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="7" fill="#0E1424" />
      <g fill="#00FFB2">
        <rect x="6" y="17" width="3.5" height="9" rx="1" />
        <rect x="12" y="11" width="3.5" height="15" rx="1" />
        <rect x="18" y="14" width="3.5" height="12" rx="1" />
        <rect x="24" y="7" width="3.5" height="19" rx="1" />
      </g>
    </svg>
  );
}
