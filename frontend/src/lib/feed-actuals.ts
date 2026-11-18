import { call, type Envelope } from "@/lib/frappe";

/* ── A herd's feed day: the recipe is the plan, what was fed is the actual ──
   Wire shapes of serverscripts/feeding/feed_actuals.py and
   daily_feed_report.py. Kilogram figures throughout, except a per-head dose
   row, which is in its own unit (`uom`). */

export type DayComponent = {
  item_code: string;
  item_name: string;
  uom: string;
  planned_kg: number;
  actual_kg: number;
  planned_per_head: number;
  actual_per_head: number;
  /** Left out of the day: planned, but fed none (actual 0). Not manufactured. */
  removed: boolean;
};

export type HerdDay = {
  herd: string;
  herd_name: string;
  date: string;
  record: string | null;
  bom: string;
  head_count: number;
  status: "Planned" | "Amended" | "Waiting for stock" | "Manufactured";
  amended: boolean;
  planned_kg: number;
  actual_kg: number;
  planned_per_head: number;
  actual_per_head: number;
  variance_kg: number;
  components: DayComponent[];
  draft_entries: string[];
  remarks: string | null;
  pending?: boolean;
  waiting_for?: string | null;
};

export type FeedDayProgram = {
  date: string;
  herds: HerdDay[];
  skipped: Array<{ herd: string; reason: string }>;
  setup: string[];
};

export type AnimalIntake = {
  herd: string;
  date: string;
  head_count: number;
  planned_kg: number;
  actual_kg: number;
  variance_kg: number;
  variance_pct: number;
  appetite: Appetite;
  totals: AppetiteTotals;
  animals: Array<{
    animal: string;
    tag: string;
    planned_kg: number;
    actual_kg: number;
    variance_kg: number;
    variance_pct: number;
    appetite: Appetite;
  }>;
};

/** No threshold: below the plan, above it, or on it (to 0.01 kg). */
export type Appetite = "below" | "above" | "on_plan";

/** Planned and actual kg, and how many animals fell in each group. */
export type AppetiteTotals = {
  planned_kg: number;
  actual_kg: number;
  below_plan: number;
  above_plan: number;
  on_plan: number;
};

export type ReportAnimal = {
  animal: string;
  tag: string;
  herd: string;
  planned_kg: number;
  actual_kg: number;
  variance_kg: number;
  variance_pct: number;
  appetite: Appetite;
  last_weight: number | null;
  last_weight_date: string | null;
  adg: number | null;
};

export type DailyFeedReport = {
  date: string;
  herds: Array<{
    herd: string;
    herd_name: string;
    head_count: number;
    planned_kg: number;
    actual_kg: number;
    amended: boolean;
    draft_entries: string[];
    components: Array<{
      item_code: string;
      item_name: string;
      uom: string;
      planned_kg: number;
      actual_kg: number;
    }>;
  }>;
  animals: ReportAnimal[];
  totals: AppetiteTotals;
};

const BASE = "upande_livestock.serverscripts.feeding.";

export function feedDayProgram(date: string, herd?: string): Promise<Envelope<FeedDayProgram>> {
  return call(`${BASE}feed_actuals.feed_day_program`, { date, herd });
}

export function amendFeedDay(
  herd: string,
  date: string,
  components: Array<{ item_code: string; actual_kg: number }>,
  remarks?: string,
): Promise<Envelope<HerdDay>> {
  return call(`${BASE}feed_actuals.amend_feed_day`, {
    herd,
    date,
    components: JSON.stringify(components),
    remarks,
  });
}

/** Put a herd's day back to the recipe (drops the amendment). Refused once mixed. */
export function resetFeedDay(herd: string, date: string): Promise<Envelope<HerdDay>> {
  return call(`${BASE}feed_actuals.reset_feed_day`, { herd, date });
}

export function manufactureFeedActuals(herd: string, date: string): Promise<Envelope<HerdDay>> {
  return call(`${BASE}feed_actuals.manufacture_feed_actuals`, { herd, date });
}

export function animalIntake(herd: string, date: string): Promise<Envelope<AnimalIntake>> {
  return call(`${BASE}feed_actuals.animal_intake`, { herd, date });
}

export function dailyFeedReport(date: string, herd?: string): Promise<Envelope<DailyFeedReport>> {
  return call(`${BASE}daily_feed_report.daily_feed_report`, { date, herd });
}

/** What the amend box shows for a kg figure, without trailing noise. */
export function kgText(n: number): string {
  return String(Math.round(n * 1000) / 1000);
}

export function pctText(n: number): string {
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

export const APPETITE_LABEL: Record<Appetite, string> = {
  below: "Below plan",
  above: "Above plan",
  on_plan: "On plan",
};
