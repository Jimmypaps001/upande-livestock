/**
 * The Animals page's data, all of it now off the server.
 *
 * Two calls rather than one: the search list is redrawn as somebody types and
 * the profile walks an animal's whole event history, so asking for both
 * together would make the page as slow as its slowest cow.
 */
import { call, type Envelope } from "@/lib/frappe";
import type { AnimalProfile, AnimalSummary, CoverDetail } from "@/lib/animals";

const MARK = "upande_livestock.serverscripts.animals.mark_cull_review.mark_cull_review";
const LIST = "upande_livestock.serverscripts.animals.animal_list.animal_list";
const PROFILE = "upande_livestock.serverscripts.animals.animal_profile.animal_profile";
const BENCH = "upande_livestock.serverscripts.animals.herd_benchmarks.herd_benchmarks";

export function markCullReview(animal: string, reason: string, marked = true) {
  return call<{ animal: string; marked: boolean; on: string | null }>(MARK, {
    payload: { animal, reason, marked },
  });
}

export function getAnimals(): Promise<Envelope<{ animals: AnimalSummary[] }>> {
  return call<{ animals: AnimalSummary[] }>(LIST, {});
}

export function getAnimalProfile(animal: string): Promise<Envelope<AnimalProfile>> {
  return call<AnimalProfile>(PROFILE, { payload: { animal } });
}

const COVER = "upande_livestock.serverscripts.animals.animal_cover";

export interface CoverPolicy {
  name: string;
  policy_number: string | null;
  policy_type: string;
  insurer_name: string | null;
  start_date: string;
  end_date: string;
}

export function getAnimalCover(animal: string) {
  return call<CoverDetail>(`${COVER}.animal_cover`, { payload: { animal } });
}

export function getCoverPolicies(animal: string) {
  return call<{ available: boolean; policies: CoverPolicy[] }>(`${COVER}.cover_policies`, {
    payload: { animal },
  });
}

/** Add her Asset to a running Upande Asset policy; Upande Asset decides who may. */
export function insureAnimal(p: {
  animal: string;
  policy: string;
  sum_insured?: number;
  effective_date?: string;
  endorsement_no?: string;
}) {
  return call<{ asset: string; status?: string; endorsement_group?: string }>(`${COVER}.insure_animal`, {
    payload: p,
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
