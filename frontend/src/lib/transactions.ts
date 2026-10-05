import { call } from "@/lib/frappe";

const NS = "upande_livestock.serverscripts.transactions";

/** A livestock stock issue saved as a draft because the store could not cover
 *  it on the day the event was recorded. */
export interface StockDraft {
  name: string;
  posting_date: string;
  /** "Livestock Vaccination" — the event the issue is for. */
  stock_entry_type: string;
  remarks: string | null;
  made_by: string;
  /** The record that made it, when it still stands. */
  source: { doctype: string; name: string; animal: string | null; event_type: string } | null;
  items: { item_code: string; item_name: string; qty: number; uom: string; warehouse: string }[];
  /** Whether the store holds enough of every line right now. */
  can_post: boolean;
  /** What is still missing, in words, when it cannot. */
  short: string | null;
}

export const fetchStockDrafts = () => call<{ drafts: StockDraft[] }>(`${NS}.stock_drafts.stock_drafts`);

export const postStockDraft = (name: string) =>
  call<{ name: string }>(`${NS}.post_stock_draft.post_stock_draft`, { payload: { name } });
