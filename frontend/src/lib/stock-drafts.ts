/**
 * What an endpoint's answer carries when its record stood but its stock issue
 * was saved as a draft for want of stock — and how the app says so.
 *
 * Imports nothing on purpose: the toast (on every page) reads it, and pulling
 * the server client in through here would tie every page's toast to it.
 */

export interface DraftMade {
  name: string;
  stock_entry_type: string;
  short: string;
}

/** Fired on `window` by lib/frappe's `call`, heard by the toast. */
export const DRAFTS_EVENT = "livestock:stock-drafts";

/** The sentence shown when a record stood but its stock did not move. */
export function draftSentence(d: DraftMade): string {
  return `Recorded, but the store cannot cover it yet (${d.short}). ${d.name} (${d.stock_entry_type}) is saved as a draft — post it from Transactions once the stock is in.`;
}
