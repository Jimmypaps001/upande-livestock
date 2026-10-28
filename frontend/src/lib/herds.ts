/**
 * Composing a herd: splitting one off the animals you have, and buying one in.
 *
 * Both are the same kind of act — deciding which animals stand together — and
 * both go through a Movement event on the server rather than a write to
 * `current_herd`, so an animal's timeline can always answer where she was and
 * who moved her.
 */
import { call, type Envelope } from "@/lib/frappe";

const UPDATE = "upande_livestock.serverscripts.herds.update_herd.update_herd";
const LADDER = "upande_livestock.serverscripts.herds.save_band_ladder.save_band_ladder";
const CREATE = "upande_livestock.serverscripts.herds.create_herd.create_herd";
const BUY_IN = "upande_livestock.serverscripts.herds.buy_in_animal.buy_in_animal";
const RATION = "upande_livestock.serverscripts.feeding.set_herd_ration.set_herd_ration";

export interface RationLine {
  item_code: string;
  qty: number;
}

export interface RationResult {
  bom: string;
  changed: boolean;
  superseded: string | null;
  per_head_kg: number;
  item: string;
}

export const HERD_CLASSES = ["Breeding", "Fattening", "Calf", "Cow", "Other"] as const;
export type HerdClass = (typeof HERD_CLASSES)[number];

/** What the editor holds while it is being typed: strings, because a number
 *  box hands back text and a blank has to stay blank. */
export type HerdDetails = {
  herd_class: HerdClass;
  min_weight_kg: string;
  max_weight_kg: string;
  target_adg_kg: string;
  weigh_monthly: boolean;
  /** Whether the person (or a class change on their behalf) has settled the
   *  weighing box. Untouched, it is not sent and the server's default applies. */
  weigh_touched?: boolean;
};

/** Classes the server weighs monthly unless told otherwise. */
export const WEIGH_MONTHLY_CLASSES: readonly HerdClass[] = ["Fattening", "Breeding"];

/** The details after the class changes: a Fattening or Breeding herd is
 *  weighed monthly by default, ticked here so the person sees it and can untick. */
export function withClass(d: HerdDetails, herd_class: HerdClass): HerdDetails {
  const next = { ...d, herd_class };
  if (WEIGH_MONTHLY_CLASSES.includes(herd_class) && !WEIGH_MONTHLY_CLASSES.includes(d.herd_class)) {
    next.weigh_monthly = true;
    next.weigh_touched = true;
  }
  return next;
}

/** What the server takes. */
export type BandPayload = {
  herd_class: HerdClass;
  min_weight_kg: number;
  max_weight_kg: number;
  target_adg_kg: number;
  weigh_monthly?: 0 | 1;
};

/** Only a herd that is fattened, or reared up to the fattening bands, has a
 *  weight band; asking a breeding herd for one would invent a limit for it. */
export function showsBandFields(herdClass: string): boolean {
  return herdClass === "Fattening" || herdClass === "Calf";
}

/** A blank max means open-ended (the top band), which the server stores as 0.
 *  A class without a band clears the band (0/0); the target gain is kept as entered. */
export function bandPayload(d: HerdDetails): Partial<BandPayload> {
  const out: Partial<BandPayload> = { herd_class: d.herd_class };
  // Only a box the person settled is sent: sending 0 for an untouched one
  // reads on the server as "deliberately off" and defeats the class default.
  if (d.weigh_touched) out.weigh_monthly = d.weigh_monthly ? 1 : 0;
  out.target_adg_kg = Number(d.target_adg_kg) || 0;
  if (showsBandFields(d.herd_class)) {
    out.min_weight_kg = Number(d.min_weight_kg) || 0;
    out.max_weight_kg = Number(d.max_weight_kg) || 0;
  } else {
    // A class with no band sends 0 explicitly, so a band left over from the
    // herd's old class is cleared on the server rather than silently kept.
    out.min_weight_kg = 0;
    out.max_weight_kg = 0;
  }
  return out;
}

/** The one rule the form can say before the server does. Overlaps and gaps
 *  between herds are the server's to judge — it sees all the herds. */
export function validateBand(d: HerdDetails): string | null {
  if (!showsBandFields(d.herd_class)) return null;
  const min = Number(d.min_weight_kg) || 0;
  const max = Number(d.max_weight_kg) || 0;
  if (max && max <= min) return "The top of the band must be above its bottom.";
  return null;
}

export const emptyDetails = (): HerdDetails => ({
  herd_class: "Other",
  min_weight_kg: "",
  max_weight_kg: "",
  target_adg_kg: "",
  weigh_monthly: false,
});

export type HerdBand = {
  herd: string;
  herd_class: HerdClass;
  min_weight_kg: number | null;
  max_weight_kg: number | null;
  target_adg_kg: number | null;
  weigh_monthly: 0 | 1 | boolean;
};

export function detailsOf(h: Partial<HerdBand>): HerdDetails {
  const s = (v: number | null | undefined) => (v ? String(v) : "");
  return {
    herd_class: (h.herd_class as HerdClass) || "Other",
    min_weight_kg: s(h.min_weight_kg),
    max_weight_kg: s(h.max_weight_kg),
    target_adg_kg: s(h.target_adg_kg),
    weigh_monthly: !!h.weigh_monthly,
  };
}

export function updateHerd(herd: string, d: HerdDetails) {
  return call<HerdBand>(UPDATE, { herd, ...bandPayload(d) });
}

/** One rung of the fattening ladder as the ladder editor holds it. */
export type LadderRow = { herd: string; min: string; max: string; target: string };

/** The Fattening herds, lowest band first. */
export function ladderRows(bands: HerdBand[]): LadderRow[] {
  const s = (v: number | null | undefined) => (v ? String(v) : "");
  return bands
    .filter((b) => b.herd_class === "Fattening")
    .sort((a, b) => (a.min_weight_kg || 0) - (b.min_weight_kg || 0))
    .map((b) => ({ herd: b.herd, min: s(b.min_weight_kg), max: s(b.max_weight_kg), target: s(b.target_adg_kg) }));
}

/** What save_band_ladder takes: every rung at once, a blank max as 0 (open top). */
export function ladderPayload(rows: LadderRow[]) {
  return rows.map((r) => ({
    herd: r.herd,
    min_weight_kg: Number(r.min) || 0,
    max_weight_kg: Number(r.max) || 0,
    target_adg_kg: Number(r.target) || 0,
  }));
}

/** The one rule the editor can say before the server judges the whole ladder. */
export function validateLadder(rows: LadderRow[]): string | null {
  for (const r of rows) {
    const min = Number(r.min) || 0;
    const max = Number(r.max) || 0;
    if (max && max <= min) return `${r.herd}: the top of the band must be above its bottom.`;
  }
  return null;
}

export function saveBandLadder(rows: LadderRow[]) {
  return call<{
    bands: { herd: string; min_weight_kg: number; max_weight_kg: number; target_adg_kg: number }[];
  }>(LADDER, { bands: ladderPayload(rows) });
}

export function createHerd(args: {
  herd_name: string;
  animals: string[];
  description?: string;
  ration_item?: string;
  lines?: RationLine[];
  operator?: string;
} & Partial<BandPayload>) {
  return call<{
    herd: string;
    heads: number;
    moved: { animal: string; from_herd: string | null }[];
    emptied_from: string[];
    ration: RationResult | null;
  }>(CREATE, { payload: args });
}

export function buyInAnimal(args: {
  sex: "Female" | "Male";
  herd: string;
  name_given?: string;
  breed?: string;
  date_of_birth?: string;
  arrival_date?: string;
  purchase_value?: number;
  seller?: string;
  seller_tag?: string;
  tag_number?: string;
  operator?: string;
}) {
  return call<{
    animal: string;
    name: string;
    herd: string;
    heads: number;
    asset: string | null;
    purchase_value: number;
  }>(BUY_IN, { payload: args });
}

export interface RationDifference {
  item_code: string;
  item_name: string;
  was: number;
  now: number;
  what: "added" | "dropped" | "raised" | "lowered";
}

export function setHerdRation(args: {
  herd: string;
  lines: RationLine[];
  ration_item?: string;
}) {
  return call<
    RationResult & {
      herd: string;
      heads: number;
      day_kg: number;
      differences: RationDifference[];
    }
  >(RATION, { payload: args });
}

/** What a revision did, in the words the farm would use. */
export function describeChange(d: RationDifference): string {
  if (d.what === "added") return `${d.item_name} added at ${d.now}`;
  if (d.what === "dropped") return `${d.item_name} dropped (was ${d.was})`;
  return `${d.item_name} ${d.what} from ${d.was} to ${d.now}`;
}

/* ------------------------------------------------------- reading a ration */

const RATIONS = "upande_livestock.serverscripts.feeding.herd_rations.herd_rations";

export interface RationRow {
  item_code: string;
  item_name: string;
  qty: number;
  uom: string;
}

export interface HerdRation {
  herd: string;
  heads: number;
  bom: string | null;
  ration_item: string | null;
  ration_name: string | null;
  per_head_kg: number;
  day_kg: number;
  lines: RationRow[];
  lines_total: number;
  /** Whether the stated output and the lines add up to the same number. */
  balanced: boolean;
}

export interface FeedChoice {
  value: string;
  label: string;
  uom: string;
  on_hand: number;
  /** A mix the farm makes itself rather than a raw ingredient — the one line
   *  of a TMR the concentrate page can do anything about. Decided by the feed
   *  run's own definition, so the editor and the run cannot disagree. */
  is_concentrate: boolean;
}

export interface HerdRations {
  herds: HerdRation[];
  feeds: FeedChoice[];
}

export function getHerdRations(): Promise<Envelope<HerdRations>> {
  return call<HerdRations>(RATIONS, { payload: {} });
}
