import { call, type Envelope } from "@/lib/frappe";

/**
 * What the feed stores actually hold.
 *
 * One row per item PER WAREHOUSE — deliberately not summed. The same
 * ingredient sits in more than one store on this farm, and a single total
 * hides the store that is empty, which is the one that stops a run.
 *
 * Quantities arrive in the item's stock unit (hay: BALE) and are shown in it.
 * Nothing here converts a unit; see lib/feeding.ts for why that rule is
 * absolute on this app.
 */

const FEED_IN_STORE = "upande_livestock.serverscripts.feeding.feed_in_store.feed_in_store";

export type StoreItem = {
  item_code: string;
  item_name: string;
  /** Stock unit — what the store counts in. */
  uom: string;
  qty: number;
  warehouse: string;
  is_concentrate: boolean | number;
  /** What the item is in a ration: the finished TMR, a concentrate mixed or
   *  bought to go into one, or a raw ingredient. Optional — the endpoint's
   *  first cut carried only `is_concentrate`, and this page still reads
   *  correctly against that. */
  kind?: "tmr" | "concentrate" | "ingredient";
};

export type FeedInStore = {
  warehouses: string[];
  items: StoreItem[];
};

export const ALL_WAREHOUSES = "__all__";

export function feedInStore(warehouse?: string): Promise<Envelope<FeedInStore>> {
  const args: Record<string, unknown> = {};
  if (warehouse && warehouse !== ALL_WAREHOUSES) args.warehouse = warehouse;
  return call(FEED_IN_STORE, args);
}

/**
 * Split by what the thing is, because the questions are different: a raw
 * ingredient is bought, a concentrate is mixed, and a finished ration is
 * already made and waiting for a trough. One list answers none of them.
 *
 * `kind` is preferred when the server sends it; `is_concentrate` is the
 * fallback, so this keeps working against the endpoint's first cut.
 */
export function groupStock(items: StoreItem[]): {
  rations: StoreItem[];
  concentrates: StoreItem[];
  ingredients: StoreItem[];
} {
  const rations: StoreItem[] = [];
  const concentrates: StoreItem[] = [];
  const ingredients: StoreItem[] = [];
  for (const it of items || []) {
    const kind = it.kind || (it.is_concentrate ? "concentrate" : "ingredient");
    if (kind === "tmr") rations.push(it);
    else if (kind === "concentrate") concentrates.push(it);
    else ingredients.push(it);
  }
  return { rations, concentrates, ingredients };
}

/** Total of a group, in its unit — only meaningful per unit, so the caller
 *  gets a map rather than one misleading number. */
export function totalsByUom(items: StoreItem[]): Array<{ uom: string; qty: number }> {
  const by = new Map<string, number>();
  for (const it of items || []) {
    const uom = it.uom || "";
    by.set(uom, (by.get(uom) || 0) + (Number(it.qty) || 0));
  }
  return [...by.entries()]
    .map(([uom, qty]) => ({ uom, qty }))
    .sort((a, b) => b.qty - a.qty);
}
