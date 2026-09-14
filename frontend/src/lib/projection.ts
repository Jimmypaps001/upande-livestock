/**
 * When each feed runs out.
 *
 * The server answers in the store's own units — hay in bales, silage in
 * kilograms — and this file does not convert. Feed units are the one thing
 * this app has been burnt by twice: a recipe written in kilograms against an
 * item stocked in bales is a fourteen-fold error that reads as plausible.
 */
import { call, type Envelope } from "@/lib/frappe";

const PROJECTION = "upande_livestock.serverscripts.feeding.feed_projection.feed_projection";

export interface HerdDraw {
  herd: string;
  heads: number;
  per_head: number;
  per_day: number;
}

export interface ConcentrateDraw {
  concentrate: string;
  per_day: number;
}

export interface ProjectedItem {
  item_code: string;
  item_name: string;
  uom: string;
  on_hand: number;
  per_day: number;
  direct_per_day: number;
  via_concentrate_per_day: number;
  days_cover: number | null;
  runs_out_on: string | null;
  within_horizon: boolean;
  herds: HerdDraw[];
  concentrates: ConcentrateDraw[];
  /** Stock left on each day ahead, floored at nothing. A store stops; it does
   *  not go negative. */
  series: number[];
}

export interface FeedProjection {
  start: string;
  days: number;
  dates: string[];
  items: ProjectedItem[];
  running_out: ProjectedItem[];
  basis: string;
}

export function getFeedProjection(days = 30): Promise<Envelope<FeedProjection>> {
  return call<FeedProjection>(PROJECTION, { payload: { days } });
}

/**
 * How worried to be about a feed, in the farm's terms rather than a percentage.
 *
 * The bands are about lead time, not about proportion of stock: a feed that is
 * 5% full is fine if nothing eats it, and one that is 80% full is an emergency
 * if it goes in four days and the supplier takes a week.
 */
export type Urgency = "gone" | "days" | "week" | "fine";

export function urgencyOf(item: ProjectedItem): Urgency {
  const d = item.days_cover;
  if (d === null) return "fine";
  if (d <= 0) return "gone";
  if (d < 4) return "days";
  if (d < 10) return "week";
  return "fine";
}

export const URGENCY_TONE: Record<Urgency, string> = {
  gone: "var(--sd-sev-critical)",
  days: "var(--sd-sev-critical)",
  week: "var(--sd-sev-moderate)",
  fine: "var(--sd-data-cyan)",
};

export function urgencyWords(item: ProjectedItem): string {
  const d = item.days_cover;
  if (d === null) return "nothing draws it";
  if (d <= 0) return "none left";
  if (d < 1) return "gone today";
  if (d < 2) return "gone tomorrow";
  return `${Math.floor(d)} days left`;
}

/* ------------------------------------------------------------------ buying */

const PROCUREMENT = "upande_livestock.serverscripts.feeding.feed_procurement.feed_procurement";
const REQUEST = "upande_livestock.serverscripts.feeding.create_feed_request.create_feed_request";

export interface BuyLine {
  item_code: string;
  item_name: string;
  uom: string;
  on_hand: number;
  per_day: number;
  days_cover: number | null;
  runs_out_on: string | null;
  target_days: number;
  order_qty: number;
  /** "Raw material" or "Bought in". Never a concentrate the farm mixes. */
  source: string;
}

export interface OpenRequest {
  name: string;
  transaction_date: string;
  status: string;
  line_count: number;
  total_qty: number;
}

export interface Procurement {
  target_days: number;
  items: BuyLine[];
  warehouse: string | null;
  basis: string;
  open_requests: OpenRequest[];
}

export function getProcurement(targetDays = 28): Promise<Envelope<Procurement>> {
  return call<Procurement>(PROCUREMENT, { payload: { target_days: targetDays } });
}

export function createFeedRequest(args: {
  items: { item_code: string; qty: number }[];
  target_days?: number;
  warehouse?: string;
  schedule_date?: string;
}) {
  return call<{
    name: string;
    warehouse: string;
    schedule_date: string;
    lines: number;
    farm: string | null;
  }>(REQUEST, { payload: args });
}
