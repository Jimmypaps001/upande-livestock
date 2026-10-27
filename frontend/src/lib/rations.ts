import { call, type Envelope } from "@/lib/frappe";
import type { RecipeLine } from "@/lib/feeding";

/**
 * The ration record: which recipe a herd was fed, on what day, and how much.
 *
 * One rule this module exists to keep.
 *
 * **The recipe is the one the run cited, not the herd's current one.** The
 * server reads `bom_no` off the Work Order; nothing here may substitute the
 * herd's standing ration, or a recipe change would rewrite the whole history.
 * That is why `bom_no` travels beside `recipe` everywhere: "TMR Calves Meal"
 * names four different mixes over this farm's year, and only the BOM number
 * tells them apart.
 */

const RATION_HISTORY =
  "upande_livestock.serverscripts.feeding.ration_history.ration_history";

export const ALL_HERDS = "__all__";

export type RationRow = {
  /** The day the mix was made, as `YYYY-MM-DD`. */
  fed_on: string;
  herd: string;
  herd_label: string;
  /** The BOM the run actually used — the only thing that separates one
   *  "TMR Calves Meal" from the next. */
  bom_no: string;
  item_code: string;
  recipe: string;
  ration_kind: string;
  /** Summed across every run of that recipe on that day. */
  qty: number;
  uom: string;
  runs: number;
  heads: number;
  feed_mode: string;
  /** This recipe's ingredients — item, quantity, unit — in RECIPE uom, never
   *  converted here (see `IngredientLines`). `undefined` when the endpoint
   *  has not been extended to carry them (as opposed to `[]`, a run with none
   *  recorded) — the Rations page tells those two apart. */
  lines?: RecipeLine[];
};

export type RationHistory = {
  rows: RationRow[];
  herds: Array<{ herd: string; label: string }>;
  from_date: string;
  to_date: string;
  limit: number;
  truncated: boolean;
};

export function rationHistory(args: {
  herd?: string;
  fromDate?: string;
  toDate?: string;
  limit?: number;
}): Promise<Envelope<RationHistory>> {
  const payload: Record<string, unknown> = {};
  if (args.herd && args.herd !== ALL_HERDS) payload.herd = args.herd;
  if (args.fromDate) payload.from_date = args.fromDate;
  if (args.toDate) payload.to_date = args.toDate;
  if (args.limit) payload.limit = args.limit;
  return call(RATION_HISTORY, payload);
}

/**
 * Rows grouped by herd, each herd's days newest first.
 *
 * The question the farm asked was "for Finishing group 1 we have had these
 * recipes so far" — that is a herd's story read down a page, not a date-sorted
 * mixture of nine herds. Herds keep the order the server sent them in (newest
 * feeding first), so the herd fed most recently leads.
 */
export function groupByHerd(
  rows: RationRow[],
): Array<{ herd: string; label: string; rows: RationRow[] }> {
  const order: string[] = [];
  const by = new Map<string, RationRow[]>();
  for (const row of rows || []) {
    if (!by.has(row.herd)) {
      by.set(row.herd, []);
      order.push(row.herd);
    }
    by.get(row.herd)!.push(row);
  }
  return order.map((herd) => {
    const group = by.get(herd)!;
    return {
      herd,
      label: group[0].herd_label || herd,
      rows: [...group].sort((a, b) => b.fed_on.localeCompare(a.fed_on)),
    };
  });
}

/**
 * Every distinct recipe a set of rows used, newest first — what "these are the
 * recipes we have had so far" actually means.
 *
 * Keyed on `bom_no`, never on the recipe's name: this farm's three
 * "TMR Calves Meal" BOMs would collapse into one line and the history would
 * claim a single unchanged recipe.
 */
export function recipesUsed(
  rows: RationRow[],
): Array<{ bom_no: string; recipe: string; days: number; last_fed: string; qty: number }> {
  const by = new Map<string, { bom_no: string; recipe: string; days: number; last_fed: string; qty: number }>();
  for (const row of rows || []) {
    const seen = by.get(row.bom_no);
    if (!seen) {
      by.set(row.bom_no, {
        bom_no: row.bom_no,
        recipe: row.recipe,
        days: 1,
        last_fed: row.fed_on,
        qty: Number(row.qty) || 0,
      });
      continue;
    }
    seen.days += 1;
    seen.qty += Number(row.qty) || 0;
    if (row.fed_on > seen.last_fed) seen.last_fed = row.fed_on;
  }
  return [...by.values()].sort((a, b) => b.last_fed.localeCompare(a.last_fed));
}
