import { call, type Envelope } from "@/lib/frappe";

/* ── Wire shapes ────────────────────────────────────────────────────────────
   Named after the keys the endpoints already return; nothing is renamed on
   the way in, so a field can be traced from the screen straight to the
   serverscript that produced it. */

export type HerdOption = { name: string; label: string; heads: number; bom: string };

export type FeedLine = {
  item_code: string;
  item_name: string;
  /** STOCK unit — what the store counts in (hay: BALE). */
  uom: string;
  required_qty: number;
  /** RECIPE unit amount for the whole herd — what the mixer works to (hay: kg). */
  recipe_qty: number;
  recipe_uom: string;
  conversion_factor: number;
  source_warehouse: string | null;
  available: number;
  available_elsewhere: number;
  short_qty: number;
  is_concentrate: boolean;
  concentrate_source: string | null;
  bom_no: string | null;
};

export type ConcentratePlanCard = {
  item_code: string;
  item_name: string;
  uom: string;
  source: string;
  bom_no: string | null;
  needed: boolean;
  required_qty: number;
  short_qty: number;
  batch_qty: number;
  batches: number;
  plan_qty: number;
  available: number;
  available_elsewhere: number;
  source_warehouse: string | null;
  lines: FeedLine[];
  shortages: FeedLine[];
  can_manufacture: boolean;
};

export type FeedingProgram = {
  herd: string;
  herd_label: string;
  bom_no: string;
  production_item: string;
  production_item_name: string;
  heads: number;
  per_head_qty: number;
  total_manufacture_qty: number;
  uom: string;
  store: string;
  available_in_store: number;
  lines: FeedLine[];
  shortages: FeedLine[];
  concentrates: ConcentratePlanCard[];
  can_manufacture: boolean;
};

export type FeedDayStatus = {
  herd: string;
  heads: number;
  ration_item: string;
  runs_per_day: number;
  day_qty: number;
  issued_today: number;
  remaining_today: number;
  runs_done: number;
  suggested_portion: number;
  per_head_kg: number;
  day_kg: number;
  issued_kg: number;
  remaining_kg: number;
  complete: boolean;
};

export type FeedRunResult = {
  work_order: string;
  issue_stock_entry: string;
  produced_qty: number;
  issued_qty: number;
  uom: string;
  feed_mode?: string;
  heads: number;
  portion: number;
};

export type ConcentrateWeeklyRow = {
  item_code: string;
  item_name: string;
  bom_no: string;
  per_day_kg: number;
  needed_kg: number;
  on_hand_kg: number;
  to_mix_kg: number;
  batches: number;
  days_cover: number | null;
  can_mix: boolean;
  short: Array<{ item_name?: string; item_code?: string }>;
  herds: unknown;
};

export type ConcentrateWeeklyPlan = {
  days: number;
  batch_kg: number;
  concentrates: ConcentrateWeeklyRow[];
  total_to_mix_kg: number;
  total_batches: number;
};

/* ── Endpoints ─────────────────────────────────────────────────────────────
   `record_feeding` is the one frozen path for the herd feed screen: the
   phone (and now this page) does not have to know that manufacturing and
   issuing are separate endpoints, or that they moved. */

const RECORD_FEEDING = "upande_livestock.serverscripts.mobile.record_feeding.record_feeding";
const MANUAL_FEED = "upande_livestock.serverscripts.feeding.manual_feed.manual_feed";
const CONCENTRATE_PLAN =
  "upande_livestock.serverscripts.feeding.concentrate_plan.concentrate_plan";
const FEED_OPTIONS = "upande_livestock.serverscripts.feeding.feed_options.feed_options";

export function feedOptions(): Promise<Envelope<{ herds: HerdOption[] }>> {
  return call(FEED_OPTIONS, {});
}

export function feedingProgram(herd: string): Promise<Envelope<FeedingProgram>> {
  return call(RECORD_FEEDING, { payload: { action: "info", herd } });
}

export function feedDayStatus(herd: string): Promise<Envelope<FeedDayStatus>> {
  return call(RECORD_FEEDING, { payload: { action: "day", herd } });
}

/** Mix and issue the herd's own ration. `portion` is 0.5 (one of the day's two
 *  runs) or 1.0 (the whole day) — see PORTIONS. */
export function manufactureFeed(args: {
  herd: string;
  portion: number;
  posting_date: string;
}): Promise<Envelope<FeedRunResult>> {
  return call(RECORD_FEEDING, { payload: { action: "manufacture", ...args } });
}

/** Mix and issue a recipe the operator wrote, for a head count they counted.
 *  `lines[].qty` is per head IN THE BASE BOM'S RECIPE UOM — see seedManualRows. */
export function manualFeed(args: {
  herd: string;
  lines: Array<{ item_code: string; qty: number }>;
  heads: number;
  posting_date: string;
}): Promise<Envelope<FeedRunResult>> {
  return call(MANUAL_FEED, { payload: { ...args, portion: 1 } });
}

export function concentratePlan(days: number): Promise<Envelope<ConcentrateWeeklyPlan>> {
  return call(CONCENTRATE_PLAN, { days });
}

/* ── The two rules the screen must not break ───────────────────────────── */

export type ManualRow = {
  item_code: string;
  item_name: string;
  /** The unit `qty` is expressed in. Recipe uom for a seeded line. */
  uom: string;
  /** Per ONE head, in `uom`. */
  qty: number;
};

/**
 * Seed the manual rows from the herd's own programme.
 *
 * `qty` is the RECIPE-uom amount for ONE head. `recipe_qty` is already the
 * whole herd's requirement in the recipe uom, so dividing by the head count
 * recovers the per-head figure the base BOM itself carries.
 *
 * NEVER derive this from `required_qty`/`uom` (the stock uom), and never
 * convert between the two here. Hay is written in kg on every herd BOM but
 * stocked in BALE at 0.07 bale/kg: going through the stock uom would send the
 * server roughly 14x the intended amount and issue fourteen times the hay.
 * The server reads `lines[].qty` in the base BOM's recipe uom; the conversion
 * is its job, and only its job.
 */
export function seedManualRows(program: FeedingProgram): ManualRow[] {
  const heads = program.heads || 1;
  return (program.lines || []).map((ln) => ({
    item_code: ln.item_code,
    item_name: ln.item_name,
    uom: ln.recipe_uom,
    qty: heads ? (Number(ln.recipe_qty) || 0) / heads : 0,
  }));
}

/**
 * The only two portions the screen offers.
 *
 * The farm feeds twice a day, so a run is half the day or the whole of it.
 * The switch carries these; the operator never types a decimal and never
 * sees one — they see the kilograms the choice produces.
 */
export const PORTIONS = [
  { portion: 0.5, label: "Half day" },
  { portion: 1, label: "Full day" },
] as const;

/** Kilograms this run would put in the trough, live as the switch flips.
 *  `day_kg` is a whole day for the whole herd; the portion scales it. */
export function runKg(day: FeedDayStatus | null, portion: number): number | null {
  if (!day) return null;
  return (Number(day.day_kg) || 0) * portion;
}

/** The same run in ration units, which is what the Work Order is written in. */
export function runRationQty(program: FeedingProgram | null, portion: number): number | null {
  if (!program) return null;
  return (Number(program.total_manufacture_qty) || 0) * portion;
}
