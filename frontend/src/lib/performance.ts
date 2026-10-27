import { call, isError, type Envelope } from "@/lib/frappe";

/**
 * Bull performance: who is putting weight on fastest, and who is not.
 *
 * Shapes follow the backend contract for `performance/bull_performance.py` and
 * the `beef` key of the dashboard payload. Two rules this module keeps:
 *
 *  * **An animal with too few weighings is unranked, not zero.** The server
 *    sends `period_adg: null`; showing 0.00 kg/day would read as "did not grow".
 *  * **Unranked rows sort last**, so the table starts with the animals that
 *    can be compared.
 */

const BASE = "upande_livestock.serverscripts.performance.bull_performance";
const DASHBOARD =
  "upande_livestock.serverscripts.dashboard.get_livestock_workspace_stats.get_livestock_workspace_stats";

export const PERIOD_OPTIONS = [30, 60, 90, 180] as const;
export const DEFAULT_PERIOD_DAYS = 90;
export const NOT_ENOUGH_WEIGHINGS = "Not enough weighings";

export type PerformanceRow = {
  animal: string;
  label: string;
  latest_weight_kg: number | null;
  latest_weight_date: string | null;
  days_since_weighing: number | null;
  period_adg: number | null;
  herd_adg: number | null;
  lifetime_adg: number | null;
  rank: number | null;
  below_target: boolean | null;
};

export type PerformanceView = {
  herd: string;
  herd_class: string;
  target_adg_kg: number | null;
  period_days: number;
  summary: {
    head_count: number;
    avg_weight_kg: number | null;
    avg_period_adg: number | null;
  };
  rows: PerformanceRow[];
};

export type PerformanceHerd = { herd: string; herd_class: string; head_count: number };

export function getBullPerformance(
  herd: string,
  periodDays: number = DEFAULT_PERIOD_DAYS,
): Promise<Envelope<PerformanceView>> {
  return call(`${BASE}.get_bull_performance`, { herd, period_days: periodDays });
}

/** The endpoint answers with a bare list; a refusal comes back as `{error}`. */
export async function listPerformanceHerds(): Promise<PerformanceHerd[] | { error: string }> {
  const r = await call<unknown>(`${BASE}.list_performance_herds`, {});
  if (Array.isArray(r)) return r as PerformanceHerd[];
  if (isError(r)) return r;
  const wrapped = (r as { herds?: PerformanceHerd[] } | null)?.herds;
  return Array.isArray(wrapped) ? wrapped : [];
}

/** kg/day to two places, or the words for "no figure yet". */
export function formatAdg(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return NOT_ENOUGH_WEIGHINGS;
  }
  return `${Number(value).toFixed(2)} kg/day`;
}

/** Ranked animals by rank, then the unranked in the order the server sent them. */
export function sortRows(rows: PerformanceRow[]): PerformanceRow[] {
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const ar = a.row.rank;
      const br = b.row.rank;
      if (ar === null && br === null) return a.index - b.index;
      if (ar === null) return 1;
      if (br === null) return -1;
      return ar - br || a.index - b.index;
    })
    .map((x) => x.row);
}

/** A row earns the highlight only with a ranked figure that missed the target. */
export function isHighlighted(row: PerformanceRow): boolean {
  return row.period_adg !== null && row.below_target === true;
}

/* ── The beef figures on the dashboard ─────────────────────────────────── */

export type BeefHerdTile = {
  herd: string;
  herd_class: string;
  head_count: number;
  avg_weight_kg: number | null;
  avg_adg_kg: number | null;
};

export type BeefDashboard = {
  herds: BeefHerdTile[];
  weighings_overdue: number;
  band_moves_due: number;
  ready_for_exit: number;
};

/** The dashboard payload; the beef figures are its `beef` key. */
export function getBeefDashboard(): Promise<Envelope<{ beef?: BeefDashboard }>> {
  return call(DASHBOARD, {});
}

/** Average weight to a whole kilo: a pen average to two decimals is noise. */
export function formatWeight(kg: number | null | undefined): string {
  if (kg === null || kg === undefined || !Number.isFinite(Number(kg))) return "—";
  return `${Math.round(Number(kg)).toLocaleString()} kg`;
}
