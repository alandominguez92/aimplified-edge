import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  BookOdds,
  Market,
  ParlayPick,
  PickHistoryPoint,
  PitcherProp,
  Sport,
  TrackRecord as TrackRecordType,
} from "./types.ts";
import { getHistory, getRecord, getSlate } from "./data/slate.ts";
import { marketLabels } from "./lib/market.ts";
import { probForSide } from "./lib/projection.ts";
import { TopNav } from "./components/TopNav.tsx";
import { PropTable } from "./components/PropTable.tsx";
import { PredictionCard } from "./components/PredictionCard.tsx";
import { ParlaySlip } from "./components/ParlaySlip.tsx";
import { LastUpdated } from "./components/LastUpdated.tsx";
import { TrackRecord } from "./components/TrackRecord.tsx";
import { TrackRecordChart } from "./components/TrackRecordChart.tsx";

// Poll cadence. The backend caches the slate ~5 min (the real SGO budget guard),
// so polling faster just re-reads that cache. 3 min keeps the "updated Xs ago"
// indicator honest while staying easy on the free tier; hidden tabs pause.
const POLL_MS = 180_000;

function gameKey(p: PitcherProp): string {
  return [p.team, p.opponent].sort().join("-");
}

export function App() {
  const [sport, setSport] = useState<Sport>("MLB");
  const [market, setMarket] = useState<Market>("strikeouts");
  const [props, setProps] = useState<PitcherProp[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [source, setSource] = useState<"live" | "mock" | "stale">("live");
  const [oddsAsOf, setOddsAsOf] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [record, setRecord] = useState<TrackRecordType | null>(null);
  const [history, setHistory] = useState<PickHistoryPoint[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [picks, setPicks] = useState<ParlayPick[]>([]);

  // Avoid overlapping fetches (slow network + interval + manual click).
  const inFlight = useRef(false);

  const load = useCallback(async (initial: boolean) => {
    if (inFlight.current) return;
    inFlight.current = true;
    if (initial) setLoading(true);
    else setRefreshing(true);
    try {
      const result = await getSlate(market);
      setProps(result.props);
      setSource(result.source);
      setOddsAsOf(result.asOf ?? null);
      // keep selection if it's still on the board, else jump to the first row
      setSelectedId((cur) =>
        result.props.some((p) => p.id === cur) ? cur : result.props[0]?.id,
      );
      setLastUpdated(Date.now());
      getRecord().then((r) => r && setRecord(r));
      getHistory().then(setHistory);
    } finally {
      inFlight.current = false;
      setLoading(false);
      setRefreshing(false);
    }
  }, [market]);

  useEffect(() => {
    load(true);
    const id = setInterval(() => {
      // pause polling while the tab is hidden to save the odds budget
      if (!document.hidden) load(false);
    }, POLL_MS);
    const onVisible = () => {
      if (!document.hidden) load(false);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, sport]);

  const selected = useMemo(
    () => props.find((p) => p.id === selectedId) ?? null,
    [props, selectedId],
  );

  const isPicked = (propId: string, side: "over" | "under") =>
    picks.some((p) => p.propId === propId && p.side === side);

  function handlePick(prop: PitcherProp, book: BookOdds, side: "over" | "under") {
    const data = book[side];
    if (!data) return;
    setPicks((cur) => {
      const exists = cur.some((p) => p.propId === prop.id && p.side === side);
      if (exists) {
        return cur.filter((p) => !(p.propId === prop.id && p.side === side));
      }
      const pick: ParlayPick = {
        propId: prop.id,
        pitcher: prop.pitcher,
        team: prop.team,
        opponent: prop.opponent,
        gameKey: gameKey(prop),
        book: book.book,
        side,
        line: data.line,
        odds: data.odds,
        trueProb: probForSide(prop.projection, data.line, side),
        market: prop.market ?? "strikeouts",
        last5: prop.projection.last5K,
      };
      // one side per pitcher in the slip; replace any opposite side
      return [...cur.filter((p) => p.propId !== prop.id), pick];
    });
  }

  function removePick(propId: string, side: "over" | "under") {
    setPicks((cur) => cur.filter((p) => !(p.propId === propId && p.side === side)));
  }

  return (
    <div className="min-h-screen bg-base text-ink">
      <TopNav sport={sport} onSport={setSport} />

      <div className="mx-auto max-w-[1500px] px-4 py-4">
        <div className="mb-3 flex items-center gap-3">
          <div className="flex items-center gap-0.5 rounded-lg border border-line bg-panel/40 p-0.5">
            {(["strikeouts", "hits"] as Market[]).map((m) => (
              <button
                key={m}
                onClick={() => {
                  setMarket(m);
                  setSelectedId(undefined);
                }}
                className={[
                  "rounded-md px-3 py-1 text-sm font-semibold transition-colors",
                  market === m
                    ? "bg-panel-2 text-edge"
                    : "text-ink-dim hover:text-ink",
                ].join(" ")}
              >
                {marketLabels(m).title}
              </button>
            ))}
          </div>
          <span className="rounded bg-edge/15 px-2 py-0.5 text-[11px] font-semibold uppercase text-edge">
            SIM
          </span>
          <div className="ml-auto flex items-center gap-3">
            <LastUpdated
              at={lastUpdated}
              refreshing={refreshing}
              onRefresh={() => load(false)}
            />
            {(() => {
              const staleTime = oddsAsOf
                ? new Date(oddsAsOf).toLocaleTimeString([], {
                    hour: "numeric",
                    minute: "2-digit",
                  })
                : "";
              const cfg = {
                live: {
                  cls: "bg-edge/15 text-edge",
                  label: "● live data",
                  title:
                    "Live data from MLB StatsAPI + SportsGameOdds via the backend",
                },
                stale: {
                  cls: "bg-warn/15 text-warn",
                  label: `● stale odds · as of ${staleTime}`,
                  title: `Odds feed unavailable (rate-limited) — showing last-known lines from ${staleTime}. Projections are still live.`,
                },
                mock: {
                  cls: "bg-risk/15 text-risk",
                  label: "● mock data",
                  title: "Backend unreachable — showing bundled mock slate",
                },
              }[source];
              return (
                <span
                  title={cfg.title}
                  className={[
                    "rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                    cfg.cls,
                  ].join(" ")}
                >
                  {cfg.label}
                </span>
              );
            })()}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
          {/* main table */}
          <div>
            {loading ? (
              <div className="rounded-lg border border-line bg-panel/40 p-12 text-center text-ink-dim">
                Loading today’s slate…
              </div>
            ) : (
              <PropTable
                props={props}
                market={market}
                selectedId={selectedId}
                onSelect={(p) => setSelectedId(p.id)}
                onPick={handlePick}
                isPicked={isPicked}
              />
            )}
            {history.length > 0 && (
              <div className="mt-4">
                <TrackRecordChart history={history} />
              </div>
            )}
          </div>

          {/* right rail */}
          <div className="flex flex-col gap-4 lg:sticky lg:top-[72px] lg:self-start">
            <PredictionCard prop={selected} market={market} />
            <div className="h-[320px]">
              <ParlaySlip
                picks={picks}
                onRemove={removePick}
                onClear={() => setPicks([])}
              />
            </div>
            <TrackRecord record={record} />
          </div>
        </div>

        <footer className="mt-6 border-t border-line pt-3 text-[11px] text-neutral">
          AimplifiedEdge · live data from MLB StatsAPI + SportsGameOdds, auto-refresh
          every {POLL_MS / 1000}s · projections, EV/Kelly, and sharp signals are
          model estimates for analytical use — not betting advice.
        </footer>
      </div>
    </div>
  );
}
