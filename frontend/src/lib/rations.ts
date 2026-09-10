import { call, type Envelope } from "@/lib/frappe";

/**
 * The ration record: which recipe a herd was fed, on what day, how much — and
 * the milk that followed.
 *
 * Two rules this module exists to keep.
 *
 * **The recipe is the one the run cited, not the herd's current one.** The
 * server reads `bom_no` off the Work Order; nothing here may substitute the
 * herd's standing ration, or a recipe change would rewrite the whole history.
 * That is why `bom_no` travels beside `recipe` everywhere: "TMR Calves Meal"
 * names four different mixes over this farm's year, and only the BOM number
 * tells them apart.
 *
 * **Milk sits beside the ration; it is never divided by it.** There is no
 * yield-per-kg here and there must not be one — milk comes from weeks of feed,
 * stage of lactation and the weather, not from one day's mix. The window the
 * figure came from travels with it (`milkWindowLabel`) so the column can never
 * be headed with an assumption the number does not match.
 */

const RATION_HISTORY =
  "upande_livestock.serverscripts.feeding.ration_history.ration_history";

export const ALL_HERDS = "__all__";

/** Which day's milk sits beside a ration. The server is the authority — it
 *  sends `windows` back — but these are the values it accepts today, and the
 *  default the page opens on. */
export type MilkWindow = "same_day" | "next_day" | "plus_two" | "avg_three";

export const DEFAULT_MILK_WINDOW: MilkWindow = "same_day";

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
  /** `null` when nothing was recorded in the chosen window — not zero. A herd
   *  with no milk record did not produce no milk; nobody wrote it down. */
  milk_kg: number | null;
  /** How many days of the window actually carried a recording. */
  milk_days: number;
};

export type RationHistory = {
  rows: RationRow[];
  herds: Array<{ herd: string; label: string }>;
  milk_window: MilkWindow;
  milk_window_label: string;
  milk_visible: boolean;
  windows: Array<{ value: string; label: string }>;
  from_date: string;
  to_date: string;
  limit: number;
  truncated: boolean;
};

export function rationHistory(args: {
  herd?: string;
  fromDate?: string;
  toDate?: string;
  milkWindow?: MilkWindow;
  limit?: number;
}): Promise<Envelope<RationHistory>> {
  const payload: Record<string, unknown> = {};
  if (args.herd && args.herd !== ALL_HERDS) payload.herd = args.herd;
  if (args.fromDate) payload.from_date = args.fromDate;
  if (args.toDate) payload.to_date = args.toDate;
  if (args.milkWindow) payload.milk_window = args.milkWindow;
  if (args.limit) payload.limit = args.limit;
  return call(RATION_HISTORY, payload);
}

/**
 * The milk column's heading, for the window that produced the numbers under
 * it.
 *
 * Taken from the server's own label when it sent one, so the two can never
 * disagree — a page that headed a next-day figure "milk same day" would be
 * asserting a lag the farm did not choose.
 */
export function milkColumnLabel(
  window: string,
  serverLabel?: string,
): string {
  if (serverLabel) return serverLabel;
  const fallback: Record<string, string> = {
    same_day: "milk same day",
    next_day: "milk next day",
    plus_two: "milk two days later",
    avg_three: "3-day average (day fed, +1, +2)",
  };
  return fallback[window] || "milk";
}

/**
 * Rows grouped by herd, each herd's days newest first.
 *
 * The question the farm asked was "for Lactating Group 1 we have had these
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

/** How much of a set of rows carries a milk figure at all. The page says this
 *  out loud: a mostly-empty milk column is a recording gap, not a bad harvest,
 *  and the two must not look the same. */
export function milkCoverage(rows: RationRow[]): { withMilk: number; total: number } {
  const list = rows || [];
  return {
    withMilk: list.filter((r) => r.milk_kg !== null && r.milk_kg !== undefined).length,
    total: list.length,
  };
}
