import { call, type Envelope } from "@/lib/frappe";

const NS = "upande_livestock.serverscripts.breeding";

export const SIRE_TYPES = ["Semen", "Live bull"] as const;
export type SireType = (typeof SIRE_TYPES)[number];

export interface SireRow {
  name: string;
  sire_name: string;
  code: string;
  label: string;
  sire_type: SireType;
  semen_item: string;
  /** The straw Item's name (the code when it has none). */
  semen_item_name?: string;
  animal: string;
  breed?: string;
  supplier?: string;
  sexed: number;
  active: number;
}

export interface SireInput {
  /** Present when editing: the record's name. */
  name?: string;
  sire_name: string;
  sire_code: string;
  sire_type: SireType;
  semen_item: string;
  animal: string;
  breed?: string;
  supplier?: string;
  sexed: boolean;
  active: boolean;
}

export const getSires = () => call<{ sires: SireRow[] }>(`${NS}.sires_list.sires_list`, { payload: {} });

export const saveSire = (s: SireInput) =>
  call<{ name: string }>(`${NS}.save_sire.save_sire`, {
    payload: { ...s, sexed: s.sexed ? 1 : 0, active: s.active ? 1 : 0 },
  });

export interface StrawItem {
  value: string;
  item_name: string;
  label: string;
  uom: string;
  group: string;
}

/** The Items a sire's straw can be, and the one his name or code points at. */
export const getSireItems = (sire_name: string, sire_code: string, current = "") =>
  call<{ items: StrawItem[]; suggested: StrawItem | null; group: string }>(`${NS}.sire_items.sire_items`, {
    payload: { sire_name, sire_code, current },
  });

/** Make the sire's straw Item when the store has none (Livestock Manager). */
export const createSireItem = (sire_name: string, sire_code: string) =>
  call<{ item: string }>(`${NS}.create_sire_item.create_sire_item`, { payload: { sire_name, sire_code } });

export function sireProblem(s: SireInput): string | null {
  if (!s.sire_name.trim()) return "A sire needs a name.";
  if (s.sire_type === "Live bull" && !s.animal.trim()) return "A live bull needs his animal record.";
  return null;
}

export type { Envelope };
