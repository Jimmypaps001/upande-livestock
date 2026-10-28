import { call, type Envelope } from "@/lib/frappe";

/**
 * Production forecast: when each bull reaches exit weight, what that means per
 * week, how it lines up with buyer commitments, and how past forecasts fared.
 *
 * Shapes follow the backend contract in `serverscripts/forecast/*`. Rules kept
 * here: a refusal (`{error}`) is shown verbatim, a missing figure is "—" and
 * never a zero, and a week is always the Monday that starts it.
 */

const BASE = "upande_livestock.serverscripts.forecast";
const PATH = {
  output: `${BASE}.get_output_forecast.get_output_forecast`,
  cover: `${BASE}.get_commitment_cover.get_commitment_cover`,
  trend: `${BASE}.get_productivity_trend.get_productivity_trend`,
  accuracy: `${BASE}.get_forecast_accuracy.get_forecast_accuracy`,
  save: `${BASE}.save_buyer_commitment.save_buyer_commitment`,
  list: `${BASE}.list_buyer_commitments.list_buyer_commitments`,
} as const;

export type AdgSource = "own" | "herd" | "herd_target" | "farm_target" | "none";

export type ForecastWeek = { week_start: string; head: number; kg: number };

export type ForecastBull = {
  animal: string;
  label: string;
  herd: string;
  latest_weight_kg: number | null;
  latest_weight_date: string | null;
  forecast_adg: number | null;
  adg_source: AdgSource;
  ready_date: string | null;
  ready_week: string | null;
  exit_weight_kg?: number | null;
};

export type OutputForecast = {
  exit_weight_kg: number;
  horizon_weeks: number;
  weeks: ForecastWeek[];
  bulls: ForecastBull[];
  unforecastable: number;
};

export type CoverStatus = "Gap" | "Covered" | "Surplus" | "Idle";

export type CoverRow = {
  week_start: string;
  ready_head: number;
  ready_kg: number;
  committed_head: number;
  committed_kg: number;
  carry_in_head: number;
  available_head: number;
  balance_head: number;
  status: CoverStatus;
};

export type TrendPoint = {
  week_start: string;
  avg_adg: number | null;
  head: number;
  avg_weight: number | null;
};

export type TrendSeries = { herd: string; target_adg_kg: number | null; points: TrendPoint[] };

export type TrendView = { series: TrendSeries[]; farm: TrendPoint[] };

export type AccuracyRow = {
  week_start: string;
  snapshot_date: string | null;
  forecast_head: number | null;
  actual_head: number | null;
  forecast_kg: number | null;
  actual_kg: number | null;
  error_pct_head: number | null;
  error_pct_kg: number | null;
};

export type CommitmentPayload = {
  name?: string;
  customer: string;
  week_start: string;
  head: number;
  min_weight_kg?: number | null;
  committed_kg?: number | null;
  price_per_kg?: number | null;
  notes?: string;
};

export type Commitment = {
  name: string;
  customer: string;
  week_start: string;
  head: number;
  min_weight_kg: number | null;
  committed_kg: number | null;
  price_per_kg: number | null;
  status: string;
  notes: string | null;
};

export const WEEK_OPTIONS = [8, 12, 26] as const;
export const DEFAULT_WEEKS = 12;
export const ALL_HERDS = "__all__";

export function getOutputForecast(weeks: number, herd?: string): Promise<Envelope<OutputForecast>> {
  return call(PATH.output, { weeks, ...(herd ? { herd } : {}) });
}

export function getCommitmentCover(weeks: number): Promise<Envelope<{ weeks: CoverRow[] }>> {
  return call(PATH.cover, { weeks });
}

export function getProductivityTrend(weeks: number, herd?: string): Promise<Envelope<TrendView>> {
  return call(PATH.trend, { weeks, ...(herd ? { herd } : {}) });
}

export function getForecastAccuracy(
  weeks: number,
  herd?: string,
): Promise<Envelope<{ weeks: AccuracyRow[] }>> {
  return call(PATH.accuracy, { weeks, ...(herd ? { herd } : {}) });
}

export function saveBuyerCommitment(
  payload: CommitmentPayload,
): Promise<Envelope<{ ok: true; name: string }>> {
  return call(PATH.save, { payload });
}

export function listBuyerCommitments(status?: string): Promise<Envelope<Commitment[]>> {
  return call(PATH.list, status ? { status } : {});
}

/** The Monday of the ISO week a YYYY-MM-DD date falls in (calendar maths, no timezone). */
export function mondayOf(ymd: string): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  const back = (t.getUTCDay() + 6) % 7; // Monday = 0
  t.setUTCDate(t.getUTCDate() - back);
  return t.toISOString().slice(0, 10);
}

export const ADG_SOURCE_LABEL: Record<AdgSource, string> = {
  own: "Own",
  herd: "Herd average",
  herd_target: "Herd target",
  farm_target: "Farm target",
  none: "None",
};

export function adgSourceLabel(source: string): string {
  return ADG_SOURCE_LABEL[source as AdgSource] ?? "—";
}

/** A signed percentage to one place ("+4.2%", "-12.0%"), or "—" when there is none. */
export function formatErrorPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  const pct = Number(value) * 100;
  const text = Math.abs(pct).toFixed(1);
  if (Number(text) === 0) return "0.0%";
  return `${pct > 0 ? "+" : "-"}${text}%`;
}

export function unforecastableNote(n: number): string {
  return `${n} ${n === 1 ? "bull" : "bulls"} can't be forecast yet`;
}

export const STATUS_TONE: Record<CoverStatus, "ok" | "short" | "mute"> = {
  Surplus: "mute",
  Covered: "ok",
  Gap: "short",
  Idle: "mute",
};

/** Whole numbers with thousands separators (kg to one place when it is not whole). */
export function fmtKg(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(Number(n))) return "—";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: 1 });
}
