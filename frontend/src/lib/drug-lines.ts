import type { StockChoice } from "@/lib/events";

export interface DrugLine {
  item_code: string;
  qty: string | number;
}

export interface DrugRow {
  item_code: string;
  qty: number;
  source_warehouse: string | undefined;
}

/**
 * The drug lines of a round, each drawn from the store that holds that drug.
 *
 * The form used to send one `source_warehouse` for the whole event — the
 * single `Livestock Settings.drug_warehouse` — so every line came off one
 * shelf no matter what the picker had said about where the stock was. On the
 * live site that shelf holds nothing at all; the drugs are spread across the
 * stores the farm actually uses. Each choice now carries its own warehouse
 * (`stock_items` picks the one holding the most), and it travels with the line.
 *
 * A drug the picker cannot place goes back without a warehouse, and the server
 * falls back to the configured store — which is what happened to every line
 * before this existed.
 */
export function drugRowsForIssue(lines: DrugLine[], choices: StockChoice[]): DrugRow[] {
  const where = new Map(choices.map((c) => [c.value, c.warehouse]));
  return lines
    .filter((l) => l.item_code && Number(l.qty) > 0)
    .map((l) => ({
      item_code: l.item_code,
      qty: Number(l.qty),
      source_warehouse: where.get(l.item_code),
    }));
}
