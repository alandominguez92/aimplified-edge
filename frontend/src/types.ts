// Domain types for the pitcher-prop slate. These mirror the shape the future
// FastAPI backend will return, so swapping mock data for the real API is a
// single-file change in `data/slate.ts`.

export type Sport = "MLB" | "NBA" | "NHL" | "NFL" | "Soccer";

export type Market = "strikeouts" | "hits";

export type Book =
  | "FanDuel"
  | "DraftKings"
  | "Caesars"
  | "ESPN BET"
  | "BetMGM"
  | "Bovada"
  | "Underdog";

/** One side (over or under) at one sportsbook. */
export interface BookSide {
  line: number; // e.g. 5.5
  odds: number; // American odds, e.g. -122
}

export interface BookOdds {
  book: Book;
  over?: BookSide;
  under?: BookSide;
}

export type SharpSide = "over" | "under" | null;

export interface SharpSignal {
  side: SharpSide; // which side sharp money is on
  strength: number; // 0..1; >0.6 is flagged
  ticketPct: number; // % of tickets on the OVER (public)
  openLine: number;
  currentLine: number;
}

export interface Projection {
  projectedK: number; // model point estimate
  low: number; // confidence interval bounds
  high: number;
  confidence: number; // 0..1 model confidence
  edge: number; // projectedK - marketLine (Ks); +ve favors over
  recommendedSide: "over" | "under" | null;
  last5K: number[]; // recent strikeout totals, oldest -> newest
  parkFactor: number; // 1.00 = neutral
  weather: { tempF: number; condition: "clear" | "cloudy" | "rain" | "dome" };
}

/** Forward track record aggregate (from /api/picks/record). */
export interface TrackRecord {
  totalPicks: number;
  openPicks: number;
  gradedPicks: number;
  wins: number;
  losses: number;
  pushes: number;
  record: string;
  hitRate: number | null;
  unitsProfit: number;
  roiPct: number | null;
  avgClv: number | null;
}

/** One graded pick in the performance history (/api/picks/history). */
export interface PickHistoryPoint {
  day: string;
  pitcher: string;
  side: "over" | "under";
  line: number;
  odds: number;
  result: "win" | "loss" | "push";
  profitUnits: number;
  clv: number | null;
  cumulativeUnits: number;
}

/** Result of /api/parlay — computed by the C++ EV engine. */
export interface ParlayEval {
  american: number;
  naiveProb: number;
  corrProb: number;
  naiveEv: number;
  corrEv: number;
  corrPairs: number;
  maxExposure: number;
  engine: string;
}

/** A leg added to the parlay slip. */
export interface ParlayPick {
  propId: string;
  pitcher: string;
  team: string;
  opponent: string;
  gameKey: string; // normalized matchup, for correlation checks
  book: Book;
  side: "over" | "under";
  line: number;
  odds: number;
  trueProb: number; // model probability for this leg
}

export interface PitcherProp {
  id: string;
  market?: Market; // "strikeouts" | "hits" — reused shape; `pitcher` = player
  gameTime: string; // ISO timestamp
  pitcher: string;
  team: string; // pitcher's team abbr
  opponent: string; // opponent abbr
  isHome: boolean;
  marketLine: number; // consensus line, the table's headline number
  books: BookOdds[];
  projection: Projection;
  sharp: SharpSignal;
}
