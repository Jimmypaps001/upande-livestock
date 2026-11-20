/**
 * What a bull has cost against what he is worth.
 *
 * The figures come from `bull_economics` on the server, which states its own
 * method (herd feed cost per day divided by the head fed that day). Nothing is
 * computed here except how the answer is worded: a missing value is "no value",
 * never a made-up zero.
 */
import { call, type Envelope } from "@/lib/frappe";

const ECON = "upande_livestock.serverscripts.animals.bull_economics";

export const BULL_PURPOSES = ["Cull for sale at birth", "Fattening", "Breeding"] as const;
export type BullPurpose = (typeof BULL_PURPOSES)[number];

export interface BullGrowth {
  kg: number | null;
  on: string | null;
  adg: number | null;
  birth_kg: number | null;
  series: { on: string; kg: number }[];
}

export interface BullEconomics {
  animal: string;
  purpose: BullPurpose;
  kept_as_cost: boolean;
  days_kept: number | null;
  feed: { cost: number; days_fed: number; per_day: number | null; method: string };
  value: { amount: number | null; source: "asset" | "price_per_kg" | null; as_of: string | null };
  net: number | null;
  burden_since: string | null;
  growth: BullGrowth | null;
  currency: string;
}

export function getBullEconomics(animal: string): Promise<Envelope<BullEconomics>> {
  return call<BullEconomics>(`${ECON}.bull_economics`, { payload: { animal } });
}

export function getBullEconomicsBulk(): Promise<
  Envelope<{ purpose: BullPurpose; bulls: Record<string, BullEconomics> }>
> {
  return call(`${ECON}.bull_economics_bulk`, {});
}

export function money(n: number | null | undefined, currency = "KES"): string {
  if (n == null) return "—";
  const sign = n < 0 ? "−" : "";
  return `${sign}${currency} ${Math.abs(Math.round(n)).toLocaleString("en-US")}`;
}

/** The marker text when running feed cost has passed his value; null when it has not. */
export function burdenMarker(e: Pick<BullEconomics, "burden_since">): string | null {
  return e.burden_since ? `Burden since ${e.burden_since}` : null;
}

/** The bull's one-line verdict, for the list and the page. */
export function verdict(e: BullEconomics): { text: string; loss: boolean } {
  if (e.net == null) return { text: `Feed ${money(e.feed.cost, e.currency)} · no value`, loss: false };
  return { text: `Net ${money(e.net, e.currency)}`, loss: e.net < 0 };
}
