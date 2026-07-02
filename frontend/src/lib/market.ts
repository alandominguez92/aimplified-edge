import type { Market } from "../types.ts";

/** Display labels for each prop market (the board reuses one component set). */
export interface MarketLabels {
  title: string;
  player: string; // table column header
  projected: string; // prediction-card headline
  propNoun: string; // "K prop" / "Hits prop"
}

const LABELS: Record<Market, MarketLabels> = {
  strikeouts: {
    title: "Pitcher Strikeouts",
    player: "Pitcher",
    projected: "Projected K",
    propNoun: "K prop",
  },
  hits: {
    title: "Batter Hits",
    player: "Batter",
    projected: "Projected H",
    propNoun: "Hits prop",
  },
};

export function marketLabels(market: Market): MarketLabels {
  return LABELS[market] ?? LABELS.strikeouts;
}
