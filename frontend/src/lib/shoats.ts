import { call, type Envelope } from "@/lib/frappe";

/**
 * Sheep and goats, kept by number. Shapes follow the Endpoints section of
 * docs/superpowers/specs/2026-10-29-mutara-shoats-design.md.
 *
 * Two rules this module keeps:
 *  * **The head is the ledger's.** Nothing here adds up a head; the server
 *    replays its events, and the page shows what it says.
 *  * **No weight is not zero.** A herd with no sample has `weight_basis: "none"`;
 *    it is shown as "no sample", never as 0 kg.
 */

const G = "upande_livestock.serverscripts.shoats";

export const CLASS_KEYS = ["females", "males", "young", "others"] as const;
export type ClassKey = (typeof CLASS_KEYS)[number];
export type Head = Record<ClassKey, number> & { total: number };
export type Species = "Sheep" | "Goat";
export type WeightBasis = "class samples" | "herd sample" | "estimated" | "none";

export type ShoatHerd = {
  name: string;
  label: string;
  species: Species;
  breed: string;
  paddock: string;
  labels: Record<ClassKey, string>;
  head: Head;
  live_weight_kg: number;
  avg_weight_kg: number | null;
  weight_date: string | null;
  weight_basis: WeightBasis;
  withdrawal_until: string | null;
  in_withdrawal: boolean;
  last_count_date: string | null;
  has_ration: boolean;
  cost_center: string;
  next_due: { mating: string; expected_birth_date: string; days_to_due: number; females_served: number } | null;
  mating_status: "Pending" | "Due" | "Overdue" | null;
};

export type Totals = { herds: number; head: number; live_weight_kg: number; avg_weight_kg: number | null };

export type ShoatEvent = {
  name: string;
  event_date: string;
  event_type: string;
  females: number;
  males: number;
  young: number;
  others: number;
  born_dead: number;
  change: number;
  head_after: number;
  cause: string;
  other_herd: string;
  paddock: string;
  reason: string;
  amount: number;
  mating: string;
  variance: Record<ClassKey, number> | null;
  remarks: string;
  paired_event: string;
};

export type WeightSample = {
  name: string;
  sample_date: string;
  sample_class: string;
  animals_weighed: number;
  average_kg: number;
  total_kg: number;
};

export type Mating = {
  name: string;
  herd: string;
  species: Species;
  mating_start: string | null;
  mating_end: string | null;
  expected_birth_date: string | null;
  days_to_due: number | null;
  status: "Pending" | "Due" | "Overdue" | "Delivered";
  females_served: number;
  males_in: number;
  born_alive: number;
  born_dead: number;
  birth_rate_pct: number | null;
  births: { name: string; date: string; alive: number; dead: number }[];
};

export type Treatment = {
  name: string;
  treatment_date: string;
  treatment_type: string;
  product: string;
  product_name: string;
  dose_per_head: number;
  dose_uom: string;
  number_treated: number;
  quantity: number;
  withdrawal_days: number;
  withdrawal_end: string | null;
  diagnosis: string;
  stock_entry: string;
};

export type HerdsReply = {
  today: string;
  herds: ShoatHerd[];
  totals: { Sheep: Totals; Goat: Totals; Shoats: Totals };
  warnings: string[];
};

export type HerdReply = {
  today: string;
  herd: ShoatHerd;
  ledger: ShoatEvent[];
  weights: WeightSample[];
  matings: Mating[];
  treatments: Treatment[];
  warnings: string[];
};

export type EventType = {
  name: string;
  direction: "in" | "out" | "set" | "move" | "none";
  needs: string[];
  optional?: string[];
};

export type Options = {
  today: string;
  event_types: EventType[];
  death_causes: string[];
  treatment_types: string[];
  drug_store: string | null;
  drugs: { item_code: string; item_name: string; uom: string; qty: number }[];
  herds: { name: string; label: string; species: Species; head: number }[];
};

export const listShoatHerds = (species?: Species) =>
  call<HerdsReply>(`${G}.shoat_herds.shoat_herds`, species ? { species } : {});
export const getShoatHerd = (herd: string) => call<HerdReply>(`${G}.shoat_herd.shoat_herd`, { herd });
export const getShoatOptions = () => call<Options>(`${G}.shoat_options.shoat_options`, {});

type Written = { created: Record<string, string | null>; head?: Head; warnings: string[] };

function write(path: string, payload: Record<string, unknown>): Promise<Envelope<Written>> {
  return call<Written>(`${G}.${path}`, { payload: JSON.stringify(payload) });
}
export const recordCountEvent = (p: Record<string, unknown>) =>
  write("record_count_event.record_count_event", p);
export const recordWeightSample = (p: Record<string, unknown>) =>
  write("record_weight_sample.record_weight_sample", p);
export const recordTreatment = (p: Record<string, unknown>) =>
  write("record_treatment.record_treatment", p);
export const cancelShoatRecord = (kind: "count_event" | "treatment" | "weight_sample", name: string) =>
  write("cancel_shoat_record.cancel_shoat_record", { kind, name });

/** The weight cell: the figure, or the words for "nobody has weighed them". */
export function formatLiveWeight(h: Pick<ShoatHerd, "live_weight_kg" | "weight_basis">): string {
  if (h.weight_basis === "none" || !h.live_weight_kg) return "No sample";
  return `${Math.round(h.live_weight_kg).toLocaleString()} kg`;
}

/** Signed ledger change: "+30", "-3", "0" (a count or a mating moves nobody). */
export function formatChange(n: number): string {
  if (!n) return "0";
  return n > 0 ? `+${n}` : `−${Math.abs(n)}`;
}

/** The variance of a head count as words, or null when it agreed with the ledger. */
export function varianceNote(ev: Pick<ShoatEvent, "variance">, labels: Record<ClassKey, string>): string | null {
  if (!ev.variance) return null;
  const parts = CLASS_KEYS.filter((k) => ev.variance![k] !== 0).map(
    (k) => `${ev.variance![k] > 0 ? "+" : "−"}${Math.abs(ev.variance![k])} ${labels[k].toLowerCase()}`,
  );
  return parts.length ? parts.join(", ") : null;
}

/** The label for an event's counts: "12 ewes, 2 rams". */
export function countsText(ev: Pick<ShoatEvent, ClassKey | "event_type" | "born_dead">, labels: Record<ClassKey, string>): string {
  const parts = CLASS_KEYS.filter((k) => ev[k] > 0).map((k) => `${ev[k]} ${labels[k].toLowerCase()}`);
  if (ev.event_type === "Birth" && ev.born_dead) parts.push(`${ev.born_dead} born dead`);
  return parts.join(", ") || "—";
}
