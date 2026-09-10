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
  /** This batch's own BOM composition — item, quantity, unit, in RECIPE uom
   *  — for the row expanded open on the Concentrate page. `undefined` until
   *  `concentrate_plan` is extended to carry it: today it only returns
   *  `short`, which is the items blocking a batch, not the batch's full
   *  ingredient list, so it cannot stand in for `lines`. */
  lines?: RecipeLine[];
};

export type ConcentrateWeeklyPlan = {
  days: number;
  batch_kg: number;
  concentrates: ConcentrateWeeklyRow[];
  total_to_mix_kg: number;
  total_batches: number;
};

/** One line of a recipe, in RECIPE qty/uom — `BOM Item.qty`/`uom` for ONE
 *  head, never `stock_qty`/`stock_uom`. See herd_recipes.py's module
 *  docstring: hay is written as kg on every standing BOM but stocked in BALE
 *  at cf 0.07, so this is never converted here — it is sent to `manualFeed`
 *  exactly as it arrived. */
export type RecipeLine = { item_code: string; item_name: string; qty: number; uom: string };

/** A recipe `herd_recipes` can offer for one herd: the standing ration
 *  (`is_standing`, `kind` "Standing"), a BOM tuned for this herd before
 *  (`kind` "Tuned"), or a BOM the herd was genuinely fed before but which was
 *  never a hand-tune (`kind` "Previous" — reached only through Work Order
 *  history, per herd_recipes.py). `lines` travel with it — that is what lets
 *  a picker seed the manual tab without a second round trip.
 *
 *  `per_head_qty`/`uom` are the BOM's own header quantity/uom — the same
 *  produced item for every recipe offered for a herd (herd_recipes.py's
 *  `_runnable` only offers BOMs of the herd's standing item), so recipes are
 *  comparable to one another and to the herd's day/programme figures without
 *  any conversion. They are NOT interchangeable numbers, though: one BOM can
 *  carry a per-head amount a fraction of its siblings' (see RecipePicker's
 *  outlier check) — that difference is exactly what a bare list of recipe
 *  names would hide. */
export type Recipe = {
  bom_no: string;
  item_code: string;
  item_name: string;
  kind: string;
  is_standing: boolean;
  created: string;
  per_head_qty: number;
  uom: string;
  /** How many submitted Work Orders this herd has actually run on this
   *  recipe. 0 for a tune minted but never mixed. */
  times_fed: number;
  /** The most recent of those runs' `planned_start_date`, or "" when
   *  `times_fed` is 0. */
  last_fed: string;
  lines: RecipeLine[];
};

export type HerdRecipes = {
  herd: string;
  /** The bom_no `herd_recipes` picks as this herd's default — always the
   *  first, standing entry of `recipes`. */
  standing_bom: string;
  recipes: Recipe[];
};

/** What `manufacture_concentrate` hands back once the Work Order and its two
 *  Stock Entries exist. `ok` is always true here — a refusal comes back as
 *  `{error}` instead, per the envelope, and never reaches this shape. */
export type ConcentrateMixResult = {
  work_order: string;
  production_item: string;
  bom_no: string;
  produced_qty: number;
  store: string;
  posting_date: string;
  transfer_stock_entry: string;
  manufacture_stock_entry: string;
  uom: string;
  ok?: boolean;
};

/* ── Endpoints ─────────────────────────────────────────────────────────────
   `record_feeding` is the one frozen path for the herd feed screen: the
   phone (and now this page) does not have to know that manufacturing and
   issuing are separate endpoints, or that they moved. */

const RECORD_FEEDING = "upande_livestock.serverscripts.mobile.record_feeding.record_feeding";
const MANUAL_FEED = "upande_livestock.serverscripts.feeding.manual_feed.manual_feed";
const CONCENTRATE_PLAN =
  "upande_livestock.serverscripts.feeding.concentrate_plan.concentrate_plan";
const MANUFACTURE_CONCENTRATE =
  "upande_livestock.serverscripts.feeding.manufacture_concentrate.manufacture_concentrate";
const FEED_OPTIONS = "upande_livestock.serverscripts.feeding.feed_options.feed_options";
const HERD_RECIPES = "upande_livestock.serverscripts.feeding.herd_recipes.herd_recipes";

export function feedOptions(): Promise<Envelope<{ herds: HerdOption[] }>> {
  return call(FEED_OPTIONS, {});
}

/** A herd's standing ration plus every recipe tuned for it before — the
 *  source for the recipe picker on both tabs. Ordered standing-first, then
 *  tuned newest-first; see herd_recipes.py. */
export function herdRecipes(herd: string): Promise<Envelope<HerdRecipes>> {
  return call(HERD_RECIPES, { herd });
}

export function feedingProgram(herd: string): Promise<Envelope<FeedingProgram>> {
  return call(RECORD_FEEDING, { payload: { action: "info", herd } });
}

export function feedDayStatus(herd: string): Promise<Envelope<FeedDayStatus>> {
  return call(RECORD_FEEDING, { payload: { action: "day", herd } });
}

/** Mix and issue a herd's ration through the System path. `portion` is 0.5
 *  (one of the day's two runs) or 1.0 (the whole day) — see PORTIONS.
 *
 *  `bom_no` carries the recipe picker's choice — the herd's standing ration
 *  when omitted, or a previously-used recipe otherwise — straight to
 *  `manufacture_feed.py`, which validates it against the herd through
 *  `_base_for` before mixing. This is the only path the System tab calls: a
 *  run through here is always recorded `feed_mode="System"`, whether it
 *  reruns the standing ration or an unedited previously-used recipe. See
 *  Feeding.tsx's `mixAndFeed`. */
export function manufactureFeed(args: {
  herd: string;
  portion: number;
  posting_date: string;
  bom_no?: string;
}): Promise<Envelope<FeedRunResult>> {
  return call(RECORD_FEEDING, { payload: { action: "manufacture", ...args } });
}

/** Mix and issue a hand-tuned recipe from the Manual tab — reserved for lines
 *  the operator has actually edited; an unchanged recipe run is a System run
 *  and goes through `manufactureFeed` instead. `lines[].qty` is per head IN
 *  THE BASE BOM'S RECIPE UOM — see seedManualRows / seedRowsFromRecipe.
 *
 *  `base_bom` names the recipe this tune starts from — the herd's standing
 *  ration when omitted, or a previously-used recipe the operator picked. When
 *  `lines` reproduce `base_bom` unedited, `manual_feed.py`'s `tuned_bom`
 *  returns `base_bom` itself rather than minting a duplicate — see its module
 *  docstring. `portion` defaults to a full day; the System tab still offers
 *  the half/full switch even when it runs through here for a tuned recipe. */
export function manualFeed(args: {
  herd: string;
  lines: Array<{ item_code: string; qty: number }>;
  heads: number;
  posting_date: string;
  base_bom?: string;
  portion?: number;
}): Promise<Envelope<FeedRunResult>> {
  const { portion, ...rest } = args;
  return call(MANUAL_FEED, { payload: { ...rest, portion: portion ?? 1 } });
}

export function concentratePlan(days: number): Promise<Envelope<ConcentrateWeeklyPlan>> {
  return call(CONCENTRATE_PLAN, { days });
}

/** Run one concentrate's batch. `qty` and `bom_no` come off the plan row the
 *  operator is acting on — `to_mix_kg` by default, but the operator may raise
 *  or lower it before this is called; `can_mix` is checked by the caller
 *  before this is ever reached, never by re-asking the server. Endpoint takes
 *  its arguments directly (no `payload` wrapper) — see manufacture_concentrate.py. */
export function manufactureConcentrate(args: {
  item_code: string;
  qty: number;
  bom_no?: string | null;
}): Promise<Envelope<ConcentrateMixResult>> {
  return call(MANUFACTURE_CONCENTRATE, { ...args });
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
 * Seed the manual rows from a recipe the picker offered — the standing
 * ration by default, or one previously tuned for this herd.
 *
 * `herd_recipes` already answers in per-head recipe qty/uom (`BOM Item.qty`/
 * `uom`), the same units `seedManualRows` derives by hand above — so this is
 * a straight copy, no division and no unit conversion. NEVER convert `qty`
 * here for the same reason as `seedManualRows`: hay is written in kg on the
 * recipe but stocked in BALE at cf 0.07.
 */
export function seedRowsFromRecipe(recipe: Recipe): ManualRow[] {
  return (recipe.lines || []).map((ln) => ({
    item_code: ln.item_code,
    item_name: ln.item_name,
    uom: ln.uom,
    qty: Number(ln.qty) || 0,
  }));
}

/** An order-independent fingerprint of a row set: which items, and how much
 *  of each. Used only to ask "did the operator change anything since this
 *  was last seeded" — never sent to the server. */
function rowsFingerprint(rows: ManualRow[]): string {
  return rows
    .map((r) => `${r.item_code}:${Number(r.qty) || 0}`)
    .sort()
    .join("|");
}

/**
 * True when `current` no longer matches `seeded` — the operator has typed
 * something since the rows were last seeded from a recipe.
 *
 * This is what stands between "picking a different recipe" and "silently
 * throwing away a hand-tuned quantity nobody confirmed discarding": the
 * picker's onChange re-seeds without asking when this is false, and asks
 * first when it is true. See Feeding.tsx's `chooseRecipe`.
 */
export function manualRowsDirty(
  current: ManualRow[] | null,
  seeded: ManualRow[] | null,
): boolean {
  if (!current || !seeded) return false;
  return rowsFingerprint(current) !== rowsFingerprint(seeded);
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

/**
 * Kilograms this run would put in the trough, live as the switch flips OR
 * the recipe changes.
 *
 * For the standing ration this follows the day's own remaining-today
 * accounting exactly as before (`day.day_kg`) — a herd already fed once this
 * morning is owed the remainder, not another half. But `feed_day_status`
 * only ever answers for the herd's standing ration (`Herds.bom`); it takes
 * no `bom_no` and has no "remaining today" figure for anything else. So once
 * the operator picks a previously-used or tuned recipe instead, the preview
 * falls back to that recipe's own per-head amount times the head count —
 * exactly what a manufacture run against it would actually mix.
 *
 * `recipe.per_head_qty` is already in the produced item's own uom (see
 * `Recipe`'s docstring) — never converted here, same as everywhere else in
 * this file.
 */
export function runKg(
  day: FeedDayStatus | null,
  portion: number,
  recipe?: Recipe | null,
  heads?: number,
): number | null {
  if (recipe && !recipe.is_standing) {
    if (!heads) return null;
    return (Number(recipe.per_head_qty) || 0) * heads * portion;
  }
  if (!day) return null;
  return (Number(day.day_kg) || 0) * portion;
}

/**
 * The same run in ration units, which is what the Work Order is written in.
 *
 * Same recipe-follows-selection rule as `runKg`: the standing ration reads
 * off `program.total_manufacture_qty` (the server's own figure, batch
 * rounding included), and a previously-used or tuned recipe is recomputed
 * from its own per-head amount instead — `total_manufacture_qty` is only
 * ever the standing ration's, since `feeding_program` takes no `bom_no`
 * either.
 */
export function runRationQty(
  program: FeedingProgram | null,
  portion: number,
  recipe?: Recipe | null,
): number | null {
  if (recipe && !recipe.is_standing) {
    if (!program?.heads) return null;
    return (Number(recipe.per_head_qty) || 0) * program.heads * portion;
  }
  if (!program) return null;
  return (Number(program.total_manufacture_qty) || 0) * portion;
}
