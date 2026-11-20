import { call, type Envelope } from "@/lib/frappe";

/**
 * Weight-based asset appreciation (Settings → Asset Appreciation).
 *
 * The server does all of it — price from the matrix, the Asset Value
 * Adjustment, the idempotency. This file only starts a run and reads the
 * summary.
 */

export type AppreciationRow = {
  animal: string;
  asset: string;
  current_value: number;
  new_value: number;
  difference: number;
  status: "posted" | "would_post";
};

export type AppreciationSummary = {
  ok: boolean;
  dry_run: 0 | 1;
  animals: number;
  counts: Record<string, number>;
  total_increase: number;
  total_decrease: number;
  net: number;
  skipped_reasons: Record<string, number>;
  rows: AppreciationRow[];
};

const RUN = "upande_livestock.serverscripts.appreciation.run_appreciation.run_appreciation";

export function runAppreciation(dryRun: boolean): Promise<Envelope<AppreciationSummary>> {
  return call(RUN, { dry_run: dryRun ? 1 : 0 });
}
