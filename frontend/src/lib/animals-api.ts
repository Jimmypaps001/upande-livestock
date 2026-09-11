/**
 * The parts of the Animals page that already reach the server.
 *
 * The profile itself is still sample data; these two are real because they
 * write, and a page that pretended to mark a cow for review without marking
 * her would be worse than one that could not.
 */
import { call, type Envelope } from "@/lib/frappe";

const MARK = "upande_livestock.serverscripts.animals.mark_cull_review.mark_cull_review";
const BENCH = "upande_livestock.serverscripts.animals.herd_benchmarks.herd_benchmarks";

export function markCullReview(animal: string, reason: string, marked = true) {
  return call<{ animal: string; marked: boolean; on: string | null }>(MARK, {
    payload: { animal, reason, marked },
  });
}

export interface HerdBenchmarks {
  cows: number;
  parity: number | null;
  conception_rate: number | null;
}

export function getHerdBenchmarks(): Promise<Envelope<HerdBenchmarks>> {
  return call<HerdBenchmarks>(BENCH, {});
}

/**
 * The farm's middle cow as 0–1 per axis, in the order axesFrom returns.
 *
 * Where the server has a real median it is used; the rest are the industry
 * marks a Kenyan Ayrshire herd is measured against — a 400-day interval, an
 * SCC-clean year, three quarters of pregnancies carried. They are constants
 * until the endpoints for them exist, and they are here rather than scattered
 * through the chart so replacing them is one edit.
 */
export function benchmarkAxes(b: HerdBenchmarks | null): number[] {
  const clamp = (n: number) => Math.max(0, Math.min(1, n));
  return [
    b?.conception_rate != null ? clamp(b.conception_rate / 100) : 0.5, // fertility
    0.5, // yield — the median cow is the median by definition
    clamp((480 - 400) / 115), // interval, 400 days
    b?.parity != null ? clamp(b.parity / 6) : 0.33, // longevity
    clamp((4 - 1) / 4), // health — one treatment a year
    0.75, // carried to term
  ];
}
