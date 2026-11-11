import { call, type Envelope } from "@/lib/frappe";

/**
 * Cost per animal per day, and the daily labour book behind it.
 *
 * Shapes follow `serverscripts/costing/*`. The rules the page leans on:
 * labour, fuel and medicine are spread over every animal on the farm that day;
 * feed stays with the herd that ate it; a day with no animals has no cost per
 * animal (`null`, drawn as a dash), never a zero. A herd-day the stores never
 * issued feed for may take its cost from the farm's tracker history (Livestock
 * Feed History); those days are flagged and the page labels them, so nobody
 * mistakes the sheet's figure for a stock valuation.
 */

const BASE = "upande_livestock.serverscripts.costing";
const PATH = {
  report: `${BASE}.cost_per_animal.cost_per_animal`,
  labour: `${BASE}.daily_labour.daily_labour`,
  saveLabour: `${BASE}.save_daily_labour.save_daily_labour`,
} as const;

export type CostDay = {
  date: string;
  feed_cost: number;
  medicine_cost: number;
  labour_cost: number;
  fuel_cost: number;
  total_cost: number;
  animals: number;
  cost_per_animal: number | null;
  diesel_litres?: number;
  /** Of `feed_cost`, what came from tracker history rather than the stock ledger. */
  history_feed_cost?: number;
  feed_from_history?: boolean;
};

export type CostMonth = {
  month: string;
  days: number;
  animal_days: number;
  average_animals: number;
  feed_cost: number;
  medicine_cost: number;
  labour_cost: number;
  fuel_cost: number;
  total_cost: number;
  cost_per_animal: number | null;
  history_feed_cost?: number;
};

export type HerdFeedCost = {
  herd: string;
  feed_cost: number;
  head_days: number;
  average_heads: number;
  feed_cost_per_head_day: number | null;
  /** Days whose feed came from tracker history, and what it cost. */
  history_days?: number;
  history_feed_cost?: number;
  days: Array<{
    date: string;
    feed_cost: number;
    heads: number;
    feed_cost_per_head: number | null;
    from_history?: boolean;
  }>;
};

export type MachineWork = {
  allocation: string | null;
  machine: string | null;
  operator: string | null;
  operator_name: string | null;
  start_time: string | null;
  end_time: string | null;
  duration_hours: number;
  diesel_litres: number;
  diesel_cost: number;
  cost_center: string | null;
};

export type SilageCycle = {
  cycle: string | null;
  crop: string | null;
  silage_item: string | null;
  status: string | null;
  ensiled_kg: number;
  total_cost: number | null;
  cost_per_kg: number | null;
};

export type CostReport = {
  from_date: string;
  to_date: string;
  days: CostDay[];
  months: CostMonth[];
  herds: HerdFeedCost[];
  total: Omit<CostMonth, "month" | "average_animals">;
  fuel_available: boolean;
  fuel_note: string | null;
  production_installed: boolean;
  machines: MachineWork[];
  silage: { available: boolean; reason: string | null; cycles: SilageCycle[] } | null;
  labour_rates: Record<string, number>;
};

export type LabourRow = {
  category: string;
  workers: number;
  day_rate: number | null;
  amount?: number;
  notes?: string;
};

export type LabourDay = {
  date: string;
  saved: boolean;
  name: string | null;
  rows: LabourRow[];
  notes: string;
  categories: string[];
  default_rates: Record<string, number>;
  recent: Array<{ name: string; date: string; workers: number; amount: number }>;
  can_write: boolean;
};

export function getCostPerAnimal(fromDate: string, toDate: string): Promise<Envelope<CostReport>> {
  return call(PATH.report, { from_date: fromDate, to_date: toDate });
}

export function getDailyLabour(date: string): Promise<Envelope<LabourDay>> {
  return call(PATH.labour, { date });
}

export function saveDailyLabour(payload: {
  date: string;
  rows: LabourRow[];
  notes?: string;
}): Promise<Envelope<{ name: string; date: string; total_workers: number; total_amount: number }>> {
  return call(PATH.saveLabour, { payload });
}

/** The label on a figure that came from tracker history, not the stock ledger. */
export const HISTORY_LABEL = "from tracker history";

/** "3 days from tracker history" — a herd row's note; empty when none. */
export function historyDaysLabel(n: number | null | undefined): string {
  const k = Math.max(0, Math.trunc(Number(n) || 0));
  if (!k) return "";
  return `${k} ${k === 1 ? "day" : "days"} ${HISTORY_LABEL}`;
}

/** KES, whole shillings, thousands separated; a missing figure is a dash. */
export function fmtMoney(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || !Number.isFinite(Number(n))) return "—";
  return Number(n).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Per animal per day reads to the shilling and cents: KES 87.45. */
export const fmtPerAnimal = (n: number | null | undefined) => fmtMoney(n, 2);

/** The first and last day of the month `ym` (YYYY-MM) to report on, stopping at today. */
export function monthWindow(ym: string, today: string): { from: string; to: string } {
  const [y, m] = ym.split("-").map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const from = `${ym}-01`;
  const end = `${ym}-${String(last).padStart(2, "0")}`;
  return { from, to: end < today ? end : today };
}

/** The last `n` months as YYYY-MM, this one first. */
export function recentMonths(today: string, n = 12): string[] {
  const [y, m] = today.split("-").map(Number);
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const t = new Date(Date.UTC(y, m - 1 - i, 1));
    out.push(`${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

/** "November 2026" for "2026-11". */
export function monthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-GB", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** The first of the last `n` days to `today`: daysBack("2026-11-11", 7) is "2026-11-05". */
export function daysBack(today: string, n: number): string {
  const [y, m, d] = today.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d - (n - 1)));
  return t.toISOString().slice(0, 10);
}

/** The latest day that has animals and some cost — the Dashboard's headline day. */
export function latestCostedDay(days: CostDay[]): CostDay | null {
  for (let i = days.length - 1; i >= 0; i--) {
    if (days[i].animals > 0 && days[i].total_cost > 0) return days[i];
  }
  return null;
}

/** What a labour row comes to: workers × (its rate, else the category default). */
export function labourAmount(row: LabourRow, defaults: Record<string, number>): number {
  const rate = Number(row.day_rate) || Number(defaults[row.category]) || 0;
  return Math.max(0, Math.trunc(Number(row.workers) || 0)) * rate;
}
