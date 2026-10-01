import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Picker } from "@/components/ui/picker";
import type { StockChoice } from "@/lib/events";

/**
 * What this event used, out of the stores that actually hold it.
 *
 * Husbandry and Treatment each grew their own drug rows, so a third event
 * wanting a list had nowhere to get one — which is half the reason only four
 * of eighteen event types could consume anything. This is that list, once.
 *
 * The store is not configured anywhere. Each choice carries the warehouse
 * holding the most of it and every warehouse holding any, so picking an item
 * picks a store, and the operator can move it to another that genuinely has
 * stock. That is the whole point: a store configured apart from the item is a
 * second source of truth, and on live the two disagreed.
 */

export interface ItemRow {
  key: number;
  item: string;
  qty: string;
  store: string;
}

let nextKey = 1;

export function blankRow(): ItemRow {
  return { key: nextKey++, item: "", qty: "1", store: "" };
}

export function ItemsUsed({
  choices,
  rows,
  onChange,
}: {
  choices: StockChoice[];
  rows: ItemRow[];
  onChange: (rows: ItemRow[]) => void;
}) {
  // An event type with no mapped group consumes nothing, and a list with
  // nothing on offer is a control that can only frustrate.
  if (!choices.length) return null;

  const where = new Map(choices.map((c) => [c.value, c]));

  function set(key: number, patch: Partial<ItemRow>) {
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  return (
    <div className="flex flex-col gap-3">
      {rows.map((r) => {
        const chosen = where.get(r.item);
        return (
          <div key={r.key} className="grid gap-3 sm:grid-cols-[2fr_0.6fr_1.4fr_auto]">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`item-${r.key}`}>Item</Label>
              <Picker
                id={`item-${r.key}`}
                value={r.item}
                // Choosing the item chooses the store it is mostly in.
                onChange={(next) =>
                  set(r.key, { item: next, store: where.get(next)?.warehouse ?? "" })
                }
                options={choices.map((c) => ({ value: c.value, label: c.label }))}
                label="Item"
                placeholder="From the store…"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`qty-${r.key}`}>Qty</Label>
              <Input
                id={`qty-${r.key}`}
                type="number"
                min={0}
                step="any"
                value={r.qty}
                onChange={(e) => set(r.key, { qty: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`store-${r.key}`}>From store</Label>
              <Picker
                id={`store-${r.key}`}
                value={r.store}
                onChange={(next) => set(r.key, { store: next })}
                options={(chosen?.locations ?? []).map((l) => ({
                  value: l.warehouse,
                  label: `${l.warehouse} · ${l.qty} ${chosen?.uom ?? ""}`.trim(),
                }))}
                label="From store"
                placeholder="—"
              />
            </div>
            <div className="flex items-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={rows.length === 1}
                onClick={() => onChange(rows.filter((x) => x.key !== r.key))}
              >
                Remove
              </Button>
            </div>
          </div>
        );
      })}
      <div>
        <Button type="button" variant="outline" size="sm" onClick={() => onChange([...rows, blankRow()])}>
          Another item
        </Button>
      </div>
    </div>
  );
}
