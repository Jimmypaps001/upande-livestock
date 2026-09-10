import { call, type Envelope } from "@/lib/frappe";

/**
 * Milk production, as the dashboard reads it.
 *
 * One endpoint, unchanged: `dashboard/get_production.py` already returns the
 * recent Milk Recordings plus a 30-day summary, so nothing new was written on
 * the server for this page.
 *
 * A note on units, because it is the one thing a milk chart can get wrong:
 * this farm records milk in KILOGRAMS. Every quantity field on Milk Recording
 * is `*_kg`, and the price on Livestock Settings is per kg. Milk is a little
 * denser than water, so kilograms and litres are not the same number, and
 * nothing here converts between them — the axis says kg because the data says
 * kg.
 */

const GET_PRODUCTION = "upande_livestock.serverscripts.dashboard.get_production.get_production";

/** One Milk Recording, named exactly as the endpoint returns it. */
export type MilkRecording = {
  name: string;
  /** YYYY-MM-DD; the endpoint stringifies it. */
  recording_date: string;
  session: string;
  herd: string;
  herd_label: string;
  cows_milked: number;
  total_yield_kg: number;
  discarded_kg: number;
  net_yield_kg: number;
  discard_reason: string | null;
  protein_percent: number;
  bulk_scc: number;
  milk_revenue: number;
  custom_is_backdated: number;
};

/** The endpoint's own 30-day rollup. Every key can be missing on a failure. */
export type ProductionSummary = {
  records?: number;
  net_kg?: number;
  revenue?: number;
  discarded_kg?: number;
  avg_protein?: number;
  avg_scc?: number;
};

export type ProductionPayload = {
  rows: MilkRecording[];
  summary: ProductionSummary;
  filters: { herds?: string[]; sessions?: string[] };
};

export function getProduction(): Promise<Envelope<ProductionPayload>> {
  return call(GET_PRODUCTION, {});
}

/** A day on the chart. Milkings are per session; the chart is per day. */
export type DayPoint = {
  date: string;
  net_kg: number;
  total_kg: number;
  discarded_kg: number;
  /** How many milking sessions were recorded that day — the farm milks twice. */
  sessions: number;
  cows: number;
};

export const ALL_HERDS = "__all__";

/**
 * Recordings folded into one point per day.
 *
 * The farm milks morning and evening and files a recording for each, so a raw
 * plot of the rows draws a sawtooth that is an artefact of the milking
 * timetable, not of production. Summing the day is what a herd manager means
 * by "milk per day".
 *
 * The window is anchored on the LATEST recording rather than on the wall
 * clock: a farm that has not filed since Friday should still see its last
 * fortnight on a Monday, instead of an empty chart.
 */
export function dailySeries(
  rows: MilkRecording[],
  opts: { herd?: string; days?: number } = {},
): DayPoint[] {
  const herd = opts.herd && opts.herd !== ALL_HERDS ? opts.herd : null;
  const kept = (rows || []).filter(
    (r) => !!r.recording_date && (!herd || r.herd_label === herd || r.herd === herd),
  );
  if (!kept.length) return [];

  const byDate = new Map<string, DayPoint>();
  for (const r of kept) {
    const point = byDate.get(r.recording_date) || {
      date: r.recording_date,
      net_kg: 0,
      total_kg: 0,
      discarded_kg: 0,
      sessions: 0,
      cows: 0,
    };
    point.net_kg += Number(r.net_yield_kg) || 0;
    point.total_kg += Number(r.total_yield_kg) || 0;
    point.discarded_kg += Number(r.discarded_kg) || 0;
    point.sessions += 1;
    point.cows = Math.max(point.cows, Number(r.cows_milked) || 0);
    byDate.set(r.recording_date, point);
  }

  const days = [...byDate.values()].sort((a, b) => (a.date < b.date ? -1 : 1));
  const span = opts.days || 0;
  if (span <= 0) return days;
  const latest = days[days.length - 1].date;
  const from = shiftISO(latest, -(span - 1));
  return days.filter((d) => d.date >= from);
}

/** `iso` moved by `delta` days, still as YYYY-MM-DD. Parsed as a local date so
 *  the shift cannot slip a day across a timezone boundary. */
export function shiftISO(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, (m || 1) - 1, d || 1);
  dt.setDate(dt.getDate() + delta);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${dt.getFullYear()}-${p(dt.getMonth() + 1)}-${p(dt.getDate())}`;
}

/** Litres per cow is the number a herd manager actually compares between
 *  days, so it is derived once here rather than in the markup. */
export function perCow(point: DayPoint): number | null {
  return point.cows > 0 ? point.net_kg / point.cows : null;
}
