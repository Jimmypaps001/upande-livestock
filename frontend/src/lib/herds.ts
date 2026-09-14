/**
 * Composing a herd: splitting one off the animals you have, and buying one in.
 *
 * Both are the same kind of act — deciding which animals stand together — and
 * both go through a Movement event on the server rather than a write to
 * `current_herd`, so an animal's timeline can always answer where she was and
 * who moved her.
 */
import { call, type Envelope } from "@/lib/frappe";

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

export function createHerd(args: {
  herd_name: string;
  animals: string[];
  description?: string;
  ration_item?: string;
  lines?: RationLine[];
  operator?: string;
}) {
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
}

export interface HerdRations {
  herds: HerdRation[];
  feeds: FeedChoice[];
}

export function getHerdRations(): Promise<Envelope<HerdRations>> {
  return call<HerdRations>(RATIONS, { payload: {} });
}
