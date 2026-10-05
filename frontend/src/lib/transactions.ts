import { call } from "@/lib/frappe";

const NS = "upande_livestock.serverscripts.transactions";

/** A livestock stock entry. A draft is one the store could not cover on the
 *  day its record was made. */
export interface StockEntryRow {
  name: string;
  status: "Draft" | "Posted";
  posting_date: string;
  /** "Livestock Vaccination" — the event the issue is for. */
  stock_entry_type: string;
  remarks: string | null;
  made_by: string;
  /** The record that made it, when it still stands. */
  source: { doctype: string; name: string; animal: string | null; event_type: string } | null;
  items: { item_code: string; item_name: string; qty: number; uom: string; warehouse: string }[];
  /** A draft whose every line the store holds right now. */
  can_post: boolean;
  /** What a draft is still missing, in words. */
  short: string | null;
}

/** One day's counts on the calendar. */
export interface DayCounts {
  draft: number;
  posted: number;
}

export const fetchStockDrafts = () => call<{ drafts: StockEntryRow[] }>(`${NS}.stock_drafts.stock_drafts`);

export const fetchStockCalendar = (from_date: string, to_date: string) =>
  call<{ days: Record<string, DayCounts> }>(`${NS}.stock_calendar.stock_calendar`, {
    payload: { from_date, to_date },
  });

export const fetchStockDay = (date: string) =>
  call<{ date: string; entries: StockEntryRow[] }>(`${NS}.stock_day.stock_day`, { payload: { date } });

export const postStockDraft = (name: string) =>
  call<{ name: string }>(`${NS}.post_stock_draft.post_stock_draft`, { payload: { name } });
