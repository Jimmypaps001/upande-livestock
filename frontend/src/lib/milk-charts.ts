import { call } from "@/lib/frappe";

/**
 * The two Milking dashboard charts: yield by herd, and lab quality by batch.
 * Pure helpers here so the drawing component stays small and testable.
 */

const MILK_BY_HERD = "upande_livestock.serverscripts.milking.milk_by_herd.milk_by_herd";
const QUALITY_TREND = "upande_livestock.serverscripts.quality.quality_trend.quality_trend";

export const PERIODS = [14, 30, 90] as const;
export type Period = (typeof PERIODS)[number];

export type HerdSeries = { herd: string; kg: number[]; per_cow: (number | null)[]; total_kg: number };
export type MilkByHerd = { days: string[]; herds: HerdSeries[] };

export type QualityPoint = {
  name: string;
  date: string;
  shift: string | null;
  result: "Pass" | "Fail" | "Not assessed" | string;
  fat: number | null;
  protein: number | null;
  snf: number | null;
  ph: number | null;
  tta: number | null;
  freezing_point: number | null;
  aflatoxin: number | null;
};
export type QualityTrend = { tests: QualityPoint[] };

/** ISO date `n - 1` days before today's date, so a period of n covers n days including today. */
export function periodRange(days: number, today: Date = new Date()): { from_date: string; to_date: string } {
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const from = new Date(today);
  from.setDate(from.getDate() - (days - 1));
  return { from_date: iso(from), to_date: iso(today) };
}

export const fetchMilkByHerd = (days: number) => call<MilkByHerd>(MILK_BY_HERD, periodRange(days));
export const fetchQualityTrend = (days: number) => call<QualityTrend>(QUALITY_TREND, periodRange(days));

/** One value per day for a herd, in the unit asked for; per-cow gaps stay null. */
export function seriesValues(h: HerdSeries, perCow: boolean): (number | null)[] {
  return perCow ? h.per_cow : h.kg;
}

/** Herds with any milk in the window first, biggest first, so colours stay with the herds that matter. */
export function orderHerds(herds: HerdSeries[]): HerdSeries[] {
  return [...herds].sort((a, b) => b.total_kg - a.total_kg || a.herd.localeCompare(b.herd));
}

/** Six hues the app already uses for data, in the order they separate best. */
export const SERIES_COLOURS = [
  "var(--sd-data-indigo)",
  "var(--sd-data-cyan)",
  "var(--sd-data-pink)",
  "var(--sd-data-purple)",
  "var(--sd-data-amber)",
  "var(--sd-data-green)",
];

export const colourFor = (i: number) => SERIES_COLOURS[i % SERIES_COLOURS.length];

/** Round outward to steps a person would pick. */
export function niceRange(lo: number, hi: number): [number, number, number] {
  const span = Math.max(hi - lo, 1e-6);
  const raw = span / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step, step];
}
