import type {
  Market,
  ParlayEval,
  PickHistoryPoint,
  PitcherProp,
  TrackRecord,
} from "../types.ts";

// Backend origin. Empty = same-origin (local dev via the Vite proxy, or a
// single-service deploy where FastAPI serves this bundle). Set VITE_API_BASE at
// build time (e.g. Cloudflare Pages) to point at a separately-hosted backend,
// e.g. https://aimplified-edge.fly.dev
const API = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

// --- Mock slate -----------------------------------------------------------
// The MOCK array below is the offline fallback. `getSlate()` first tries the
// live FastAPI backend (/api/mlb/props, proxied to :8000); if it's down or
// returns nothing, the UI falls back to this fixture so it's never blank.

const TODAY = "2026-06-26";
const at = (t: string) => `${TODAY}T${t}:00`;

const MOCK: PitcherProp[] = [
  {
    id: "arrighetti-hou",
    gameTime: at("15:40"),
    pitcher: "Spencer Arrighetti",
    team: "HOU",
    opponent: "DET",
    isHome: false,
    marketLine: 5.5,
    books: [
      { book: "FanDuel", over: { line: 5.5, odds: -108 }, under: { line: 5.5, odds: -122 } },
      { book: "DraftKings", over: { line: 5.5, odds: -107 }, under: { line: 5.5, odds: -120 } },
      { book: "Underdog", under: { line: 5.5, odds: -118 } },
      { book: "BetMGM", over: { line: 5.5, odds: -105 }, under: { line: 5.5, odds: -125 } },
    ],
    projection: {
      projectedK: 6.4, low: 4.8, high: 8.0, confidence: 0.71, edge: 0.9,
      recommendedSide: "over", last5K: [7, 5, 8, 6, 9], parkFactor: 1.04,
      weather: { tempF: 81, condition: "clear" },
    },
    sharp: { side: "over", strength: 0.68, ticketPct: 41, openLine: 5.5, currentLine: 5.5 },
  },
  {
    id: "montero-det",
    gameTime: at("15:40"),
    pitcher: "Keider Montero",
    team: "DET",
    opponent: "HOU",
    isHome: true,
    marketLine: 3.5,
    books: [
      { book: "FanDuel", over: { line: 3.5, odds: -114 }, under: { line: 3.5, odds: -106 } },
      { book: "DraftKings", over: { line: 3.5, odds: -122 }, under: { line: 3.5, odds: -105 } },
      { book: "Underdog", under: { line: 3.5, odds: -106 } },
      { book: "BetMGM", over: { line: 3.5, odds: -118 }, under: { line: 3.5, odds: -104 } },
    ],
    projection: {
      projectedK: 3.1, low: 1.9, high: 4.3, confidence: 0.63, edge: -0.4,
      recommendedSide: "under", last5K: [4, 2, 3, 5, 3], parkFactor: 0.97,
      weather: { tempF: 78, condition: "dome" },
    },
    sharp: { side: null, strength: 0.32, ticketPct: 55, openLine: 3.5, currentLine: 3.5 },
  },
  {
    id: "skenes-pit",
    gameTime: at("15:40"),
    pitcher: "Paul Skenes",
    team: "PIT",
    opponent: "CIN",
    isHome: true,
    marketLine: 7.5,
    books: [
      { book: "FanDuel", over: { line: 7.5, odds: -144 }, under: { line: 7.5, odds: 118 } },
      { book: "DraftKings", over: { line: 7.5, odds: -144 }, under: { line: 7.5, odds: 113 } },
      { book: "Underdog", over: { line: 8.5, odds: 120 }, under: { line: 8.5, odds: -162 } },
      { book: "BetMGM", over: { line: 7.5, odds: -150 }, under: { line: 7.5, odds: 122 } },
    ],
    projection: {
      projectedK: 8.6, low: 6.7, high: 10.5, confidence: 0.82, edge: 1.1,
      recommendedSide: "over", last5K: [9, 11, 7, 10, 8], parkFactor: 0.99,
      weather: { tempF: 75, condition: "clear" },
    },
    sharp: { side: "over", strength: 0.79, ticketPct: 63, openLine: 7.5, currentLine: 7.5 },
  },
  {
    id: "abbott-cin",
    gameTime: at("15:40"),
    pitcher: "Andrew Abbott",
    team: "CIN",
    opponent: "PIT",
    isHome: false,
    marketLine: 4.5,
    books: [
      { book: "FanDuel", over: { line: 4.5, odds: -154 }, under: { line: 4.5, odds: 116 } },
      { book: "DraftKings", over: { line: 5.5, odds: 129 }, under: { line: 5.5, odds: -165 } },
      { book: "Underdog", over: { line: 4.5, odds: -157 } },
      { book: "BetMGM", over: { line: 4.5, odds: -150 }, under: { line: 4.5, odds: 118 } },
    ],
    projection: {
      projectedK: 4.7, low: 3.1, high: 6.3, confidence: 0.6, edge: 0.2,
      recommendedSide: null, last5K: [5, 4, 6, 4, 5], parkFactor: 1.01,
      weather: { tempF: 76, condition: "cloudy" },
    },
    sharp: { side: null, strength: 0.28, ticketPct: 49, openLine: 4.5, currentLine: 4.5 },
  },
  {
    id: "rogers-bal",
    gameTime: at("16:05"),
    pitcher: "Trevor Rogers",
    team: "BAL",
    opponent: "WAS",
    isHome: true,
    marketLine: 4.5,
    books: [
      { book: "FanDuel", over: { line: 4.5, odds: -130 }, under: { line: 4.5, odds: 106 } },
      { book: "DraftKings", over: { line: 4.5, odds: -135 }, under: { line: 4.5, odds: 106 } },
      { book: "Underdog", over: { line: 4.5, odds: -130 } },
      { book: "BetMGM", over: { line: 4.5, odds: -132 }, under: { line: 4.5, odds: 108 } },
    ],
    projection: {
      projectedK: 5.6, low: 3.9, high: 7.3, confidence: 0.74, edge: 1.1,
      recommendedSide: "over", last5K: [6, 5, 7, 4, 6], parkFactor: 1.03,
      weather: { tempF: 84, condition: "clear" },
    },
    sharp: { side: "over", strength: 0.71, ticketPct: 58, openLine: 4.5, currentLine: 4.5 },
  },
  {
    id: "alvarez-was",
    gameTime: at("16:05"),
    pitcher: "Andrew Alvarez",
    team: "WAS",
    opponent: "BAL",
    isHome: false,
    marketLine: 4.5,
    books: [
      { book: "FanDuel", over: { line: 4.5, odds: -158 }, under: { line: 4.5, odds: 118 } },
      { book: "DraftKings", over: { line: 4.5, odds: -143 }, under: { line: 4.5, odds: 112 } },
      { book: "Underdog", over: { line: 4.5, odds: -162 } },
      { book: "BetMGM", over: { line: 4.5, odds: -155 }, under: { line: 4.5, odds: 115 } },
    ],
    projection: {
      projectedK: 3.9, low: 2.4, high: 5.4, confidence: 0.58, edge: -0.6,
      recommendedSide: "under", last5K: [4, 3, 5, 3, 4], parkFactor: 0.98,
      weather: { tempF: 84, condition: "clear" },
    },
    sharp: { side: "under", strength: 0.64, ticketPct: 61, openLine: 4.5, currentLine: 4.0 },
  },
  {
    id: "eovaldi-tex",
    gameTime: at("16:07"),
    pitcher: "Nathan Eovaldi",
    team: "TEX",
    opponent: "TOR",
    isHome: false,
    marketLine: 5.5,
    books: [
      { book: "FanDuel", over: { line: 5.5, odds: 134 }, under: { line: 5.5, odds: -180 } },
      { book: "DraftKings", over: { line: 5.5, odds: 125 }, under: { line: 5.5, odds: -160 } },
      { book: "Underdog", under: { line: 4.5, odds: 124 } },
      { book: "BetMGM", over: { line: 5.5, odds: 130 }, under: { line: 5.5, odds: -170 } },
    ],
    projection: {
      projectedK: 6.5, low: 4.8, high: 8.2, confidence: 0.76, edge: 1.0,
      recommendedSide: "over", last5K: [7, 6, 8, 5, 7], parkFactor: 1.0,
      weather: { tempF: 79, condition: "dome" },
    },
    sharp: { side: "over", strength: 0.73, ticketPct: 44, openLine: 5.5, currentLine: 5.5 },
  },
  {
    id: "corbin-tor",
    gameTime: at("16:07"),
    pitcher: "Patrick Corbin",
    team: "TOR",
    opponent: "TEX",
    isHome: true,
    marketLine: 3.5,
    books: [
      { book: "FanDuel", over: { line: 3.5, odds: -172 }, under: { line: 3.5, odds: 140 } },
      { book: "DraftKings", over: { line: 3.5, odds: -171 }, under: { line: 3.5, odds: 133 } },
      { book: "BetMGM", over: { line: 3.5, odds: -175 }, under: { line: 3.5, odds: 138 } },
    ],
    projection: {
      projectedK: 3.3, low: 1.8, high: 4.8, confidence: 0.55, edge: -0.2,
      recommendedSide: null, last5K: [3, 4, 2, 4, 3], parkFactor: 1.02,
      weather: { tempF: 79, condition: "dome" },
    },
    sharp: { side: null, strength: 0.3, ticketPct: 52, openLine: 3.5, currentLine: 3.5 },
  },
  {
    id: "cantillo-cle",
    gameTime: at("16:10"),
    pitcher: "Joey Cantillo",
    team: "CLE",
    opponent: "SEA",
    isHome: true,
    marketLine: 5.5,
    books: [
      { book: "FanDuel", over: { line: 5.5, odds: 100 }, under: { line: 5.5, odds: -122 } },
      { book: "DraftKings", over: { line: 5.5, odds: -109 }, under: { line: 5.5, odds: -117 } },
      { book: "Underdog", under: { line: 5.5, odds: -121 } },
      { book: "BetMGM", over: { line: 5.5, odds: -102 }, under: { line: 5.5, odds: -120 } },
    ],
    projection: {
      projectedK: 5.9, low: 4.1, high: 7.7, confidence: 0.66, edge: 0.4,
      recommendedSide: "over", last5K: [6, 5, 7, 6, 5], parkFactor: 0.96,
      weather: { tempF: 72, condition: "clear" },
    },
    sharp: { side: null, strength: 0.41, ticketPct: 47, openLine: 5.5, currentLine: 5.5 },
  },
  {
    id: "castillo-sea",
    gameTime: at("16:10"),
    pitcher: "Luis Castillo",
    team: "SEA",
    opponent: "CLE",
    isHome: false,
    marketLine: 4.5,
    books: [
      { book: "FanDuel", over: { line: 4.5, odds: -154 }, under: { line: 4.5, odds: 116 } },
      { book: "DraftKings", over: { line: 4.5, odds: -156 }, under: { line: 4.5, odds: 122 } },
      { book: "Underdog", over: { line: 4.5, odds: -162 } },
      { book: "BetMGM", over: { line: 4.5, odds: -150 }, under: { line: 4.5, odds: 118 } },
    ],
    projection: {
      projectedK: 5.5, low: 3.8, high: 7.2, confidence: 0.78, edge: 1.0,
      recommendedSide: "over", last5K: [6, 5, 7, 6, 8], parkFactor: 0.95,
      weather: { tempF: 72, condition: "clear" },
    },
    sharp: { side: "over", strength: 0.82, ticketPct: 66, openLine: 4.5, currentLine: 5.0 },
  },
  {
    id: "tolle-bos",
    gameTime: at("16:10"),
    pitcher: "Payton Tolle",
    team: "BOS",
    opponent: "NYY",
    isHome: true,
    marketLine: 5.5,
    books: [
      { book: "FanDuel", over: { line: 5.5, odds: -114 }, under: { line: 5.5, odds: -106 } },
      { book: "DraftKings", over: { line: 5.5, odds: -135 }, under: { line: 5.5, odds: 106 } },
      { book: "BetMGM", over: { line: 5.5, odds: -120 }, under: { line: 5.5, odds: -102 } },
    ],
    projection: {
      projectedK: 6.3, low: 4.5, high: 8.1, confidence: 0.69, edge: 0.8,
      recommendedSide: "over", last5K: [7, 6, 5, 8, 6], parkFactor: 1.06,
      weather: { tempF: 83, condition: "clear" },
    },
    sharp: { side: "over", strength: 0.7, ticketPct: 59, openLine: 5.5, currentLine: 5.5 },
  },
];

export interface SlateResult {
  props: PitcherProp[];
  source: "live" | "mock" | "stale";
  asOf?: string | null; // ISO time the odds were last fetched live (stale only)
}

/**
 * Fetch today's slate from the backend, falling back to the bundled mock if the
 * API is unreachable or empty. The backend returns the exact PitcherProp shape,
 * so no mapping is needed.
 */
export async function getSlate(
  market: Market = "strikeouts",
  date?: string,
): Promise<SlateResult> {
  const path = market === "hits" ? "/api/mlb/hits" : "/api/mlb/props";
  try {
    const url = `${API}${path}${date ? `?date=${date}` : ""}`;
    const res = await fetch(url);
    if (res.ok) {
      const props = (await res.json()) as PitcherProp[];
      // A successful response is authoritative even when empty — e.g. once every
      // game has finished for the day the board should go empty, not fall back to
      // the stale mock fixture. The backend flags a stale-odds fallback (odds
      // reused because the live feed was down) via the X-Odds-As-Of header.
      const asOf = res.headers.get("X-Odds-As-Of");
      return { props, source: asOf ? "stale" : "live", asOf };
    }
  } catch {
    // backend down — fall through
  }
  // Only strikeouts has a bundled mock; hits shows an empty board when offline.
  return market === "hits"
    ? { props: [], source: "mock" }
    : { props: MOCK, source: "mock" };
}

/** Combined parlay EV from the C++ engine (naive + correlation-adjusted). */
export async function getParlay(
  legs: { prob: number; odds: number; gameKey: string }[],
): Promise<ParlayEval | null> {
  try {
    const res = await fetch(`${API}/api/parlay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(legs),
    });
    if (res.ok) return (await res.json()) as ParlayEval;
  } catch {
    // backend down
  }
  return null;
}

/** Graded-pick performance history (cumulative units). Empty until games grade. */
export async function getHistory(): Promise<PickHistoryPoint[]> {
  try {
    const res = await fetch(`${API}/api/picks/history`);
    if (res.ok) return (await res.json()) as PickHistoryPoint[];
  } catch {
    // backend down
  }
  return [];
}

/** Forward track record (ROI / hit rate / CLV). Null if the backend is down. */
export async function getRecord(): Promise<TrackRecord | null> {
  try {
    const res = await fetch(`${API}/api/picks/record`);
    if (res.ok) return (await res.json()) as TrackRecord;
  } catch {
    // backend down
  }
  return null;
}
