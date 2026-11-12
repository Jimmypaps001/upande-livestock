import { call, type Envelope } from "@/lib/frappe";

/**
 * Settings → Events: every event type, whether the farm records it at all, and
 * — for one it does — what it draws from stock and how often it comes round.
 *
 * The switch is the event type's Enabled box; the stock rule lives on the event
 * type too (a multi-select of item groups cannot sit inside a Settings
 * child-table row). "How often" is not stored here: `timings` names the
 * Livestock Settings fields that govern the event (the PD check's days after
 * service, the heat cycle, the vaccination interval...), and those are edited
 * and saved as the settings they are.
 */
export type StockRule = {
  event_type: string;
  /** Off: not recorded on this farm — hidden from the menus, no alerts, refused by the server. */
  enabled: boolean;
  posts_stock_entry: boolean;
  item_groups: string[];
  default_store: string | null;
  must_name_item: boolean;
  /** Livestock Settings fieldnames that say how often / when this event is due. */
  timings: string[];
};

export type StockRulesView = { ok: boolean; rules: StockRule[] };
export type SaveStockRulesResult = { ok: boolean; changed: string[]; rules: StockRule[] };

const NS = "upande_livestock.serverscripts.settings";

export const stockRules = (): Promise<Envelope<StockRulesView>> => call(`${NS}.stock_rules.stock_rules`);

export const saveStockRules = (rules: StockRule[]): Promise<Envelope<SaveStockRulesResult>> =>
  call(`${NS}.save_stock_rules.save_stock_rules`, { payload: { rules } });

/** Same rule? Order of the item groups matters: it is the picker's order. */
export function sameRule(a: StockRule, b: StockRule): boolean {
  return (
    a.enabled === b.enabled &&
    a.posts_stock_entry === b.posts_stock_entry &&
    a.must_name_item === b.must_name_item &&
    (a.default_store || null) === (b.default_store || null) &&
    a.item_groups.join("\u0000") === b.item_groups.join("\u0000")
  );
}

/** Why a rule cannot be saved as it stands, or null. A switched-off event is
 *  not checked: its details are kept as they were, for when it comes back on. */
export function ruleProblem(rule: StockRule): string | null {
  if (rule.enabled && rule.posts_stock_entry && rule.item_groups.length === 0) {
    return "Choose the item group it draws on.";
  }
  return null;
}

/** Are the event's details (stock, how often) shown and editable? Only while it is on. */
export function detailsShown(rule: StockRule): boolean {
  return rule.enabled;
}

/** One line for a collapsed or summarised event. */
export function ruleSummary(rule: StockRule): string {
  if (!rule.enabled) return "Switched off: not recorded, no alerts.";
  const stock = rule.posts_stock_entry
    ? `Uses stock from ${rule.item_groups.join(", ") || "no group yet"}`
    : "Uses no stock";
  return rule.timings.length ? `${stock} · has a due rule` : stock;
}
