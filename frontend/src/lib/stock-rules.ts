import { call, type Envelope } from "@/lib/frappe";

/**
 * What each event type posts to stock. The rule lives on its Livestock Event
 * Type (a multi-select of item groups cannot sit inside a Settings child-table
 * row), and the Settings screen's Stock tab edits them all in one place.
 */
export type StockRule = {
  event_type: string;
  posts_stock_entry: boolean;
  item_groups: string[];
  default_store: string | null;
  must_name_item: boolean;
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
    a.posts_stock_entry === b.posts_stock_entry &&
    a.must_name_item === b.must_name_item &&
    (a.default_store || null) === (b.default_store || null) &&
    a.item_groups.join("\u0000") === b.item_groups.join("\u0000")
  );
}

/** Why a rule cannot be saved as it stands, or null. */
export function ruleProblem(rule: StockRule): string | null {
  if (rule.posts_stock_entry && rule.item_groups.length === 0) {
    return "Choose the item group it draws on.";
  }
  return null;
}
