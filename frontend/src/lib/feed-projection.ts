import { call, type Envelope } from "@/lib/frappe";

/**
 * Feed projection: what each herd eats a day (a share of live weight), what it will eat over the next
 * weeks in a low / expected / high gain case, and how long the feed in store lasts.
 *
 * Shapes follow `serverscripts/projection/get_feed_projection`. Rules kept here: a refusal (`{error}`) is
 * shown verbatim, a figure the server could not work out is "—" and never a zero, and "days left" of null
 * means the feed outlasts the horizon.
 */

const PATH = "upande_livestock.serverscripts.projection.get_feed_projection.get_feed_projection";

export type Scenario = "low" | "expected" | "high";
export const SCENARIOS: Scenario[] = ["low", "expected", "high"];
export const SCENARIO_LABEL: Record<Scenario, string> = { low: "Low gain", expected: "Expected", high: "High gain" };
export const FEED_WEEK_OPTIONS = [4, 8, 12, 16, 26] as const;
export const DEFAULT_FEED_WEEKS = 12;

export type FeedWeek = {
  week: number;
  week_start: string;
  feed_kg: number;
  cumulative_kg: number;
  head: number;
  exits: number;
  avg_kg: number | null;
  live_kg: number;
};

export type ByScenario<T> = Record<Scenario, T>;
export type DaysLeft = ByScenario<number | null> & { today_rate: number | null };

export type FeedHerd = {
  herd: string;
  herd_class: string;
  paddock: string | null;
  counting: string;
  head: number;
  calves: number;
  fed_heads: number;
  weighed: number;
  estimated: number;
  unweighed: number;
  grows: boolean;
  live_kg: number;
  avg_kg: number | null;
  day_kg: number;
  stock_kg: number;
  paddock_stock_kg: number;
  weeks: ByScenario<FeedWeek[]> | null;
  days_left: DaysLeft | null;
};

export type BandWeek = {
  week: number;
  week_start: string;
  counts: Record<string, number>;
  exits: number;
  moves: Array<{ from: string; to: string; head: number }>;
};

export type FeedProjection = {
  as_of: string;
  weeks: number;
  settings: { dm_intake_pct: number; adg_min_kg: number; adg_max_kg: number; min_weighings: number; min_span_days: number; exit_weight_kg: number };
  total: {
    head: number;
    fed_heads: number;
    calves: number;
    live_kg: number;
    day_kg: number;
    stock_kg: number;
    weeks: ByScenario<FeedWeek[]>;
    days_left: DaysLeft;
  };
  herds: FeedHerd[];
  bands: { names: string[]; today: Record<string, number>; weeks: BandWeek[] } | null;
  stock: {
    total_kg: number;
    central_kg: number;
    items: Array<{ item_code: string; item_name: string; kg: number; warehouse: string }>;
    warehouses: Array<{ warehouse: string; kg: number; central: boolean }>;
    uncounted: Array<{ item_code: string; item_name: string; qty: number; uom: string; warehouse: string }>;
  };
  notes: string[];
};

export function getFeedProjection(weeks: number, herd?: string): Promise<Envelope<FeedProjection>> {
  return call(PATH, { weeks, ...(herd ? { herd } : {}) });
}

/** Kilograms, whole; tonnes with one decimal from 10 t up. */
export function fmtFeed(kg: number | null | undefined): string {
  if (kg === null || kg === undefined || !Number.isFinite(Number(kg))) return "—";
  const n = Number(kg);
  if (Math.abs(n) >= 10000) return `${(n / 1000).toLocaleString("en-US", { maximumFractionDigits: 1 })} t`;
  return `${Math.round(n).toLocaleString("en-US")} kg`;
}

/** Days left as the farm reads it: "25 days", "under a day", or "beyond N weeks" when it outlasts the horizon. */
export function fmtDaysLeft(days: number | null | undefined, weeks: number): string {
  if (days === null || days === undefined) return `beyond ${weeks} weeks`;
  if (days < 1) return "under a day";
  return `${Math.round(days)} days`;
}

/** The tone a days-left figure is drawn in: short of two weeks is a warning, short of one is urgent. */
export function daysTone(days: number | null | undefined): "ok" | "warn" | "short" {
  if (days === null || days === undefined) return "ok";
  if (days < 7) return "short";
  if (days < 14) return "warn";
  return "ok";
}

/** The weeks of one scenario, or none. */
export function weeksOf(h: { weeks: ByScenario<FeedWeek[]> | null }, s: Scenario): FeedWeek[] {
  return h.weeks ? h.weeks[s] : [];
}

/** The week-by-week cumulative feed against the stock: the first week the stock is gone, else null. */
export function runOutWeek(weeks: FeedWeek[], stockKg: number): number | null {
  const hit = weeks.find((w) => w.cumulative_kg > stockKg);
  return hit ? hit.week : null;
}
