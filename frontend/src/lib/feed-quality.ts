import { call } from "@/lib/frappe";

const QUALITY_VS_FEED = "upande_livestock.serverscripts.quality.quality_vs_feed.quality_vs_feed";

export interface RationLine {
  item_code: string;
  item_name: string;
  /** Per head per day, in the recipe's own unit. */
  qty: number;
  uom: string;
  concentrate: boolean;
}

export interface HerdFeedQuality {
  herd: string;
  cows: number;
  /** The herd's standing recipe; null when the herd has none. */
  ration: {
    bom: string;
    name: string;
    per_head: number;
    uom: string;
    concentrate_kg: number;
    concentrate_share: number | null;
    lines: RationLine[];
  } | null;
  /** What was actually issued to the herd in the window. */
  fed: { runs: number; kg: number };
  quality: {
    fat: number | null;
    protein: number | null;
    /** Cells per ml. */
    scc: number | null;
    readings: number;
    milkings: number;
    milk_per_cow_day: number | null;
  };
  /** Percent difference from the other milking herds together. */
  vs_rest: { fat: number | null; protein: number | null; scc: number | null };
}

export interface FeedQuality {
  days: number;
  from_date: string;
  to_date: string;
  windows: number[];
  herds: HerdFeedQuality[];
  weeks: { week: string; herds: Record<string, { fat: number | null; protein: number | null; scc: number | null }> }[];
}

export const fetchFeedQuality = (days: number) => call<FeedQuality>(QUALITY_VS_FEED, { payload: { days } });

export type Metric = "fat" | "protein" | "scc";

export const METRICS: Record<Metric, { label: string; unit: string; better: "higher" | "lower" }> = {
  fat: { label: "Butterfat", unit: "%", better: "higher" },
  protein: { label: "Protein", unit: "%", better: "higher" },
  scc: { label: "Somatic cells", unit: "k cells/ml", better: "lower" },
};

/** A metric's value as it is read: SCC in thousands, the rest as given. */
export function shown(metric: Metric, v: number | null | undefined): number | null {
  if (v == null) return null;
  return metric === "scc" ? v / 1000 : v;
}

export function formatMetric(metric: Metric, v: number | null | undefined): string {
  const s = shown(metric, v);
  if (s == null) return "—";
  return metric === "scc" ? `${Math.round(s)}k` : `${s.toFixed(2)}%`;
}
