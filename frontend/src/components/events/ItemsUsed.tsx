import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Picker } from "@/components/ui/picker";
import { Notice } from "@/components/feeding/Notice";
import type { StockChoice } from "@/lib/events";
import type { BatchPlan } from "@/lib/feeding";
import { planKey } from "@/lib/use-batch-plans";

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
  /** Empty means the rule chooses (first expiry first out). */
  batch: string;
}

let nextKey = 1;

/** `qty` is the starting quantity. A per-animal dose (Husbandry) must start
 *  blank, or an untouched 1 on a 50-head round quietly draws 50 units. */
export function blankRow(qty = "1"): ItemRow {
  return { key: nextKey++, item: "", qty, store: "", batch: "" };
}

export function ItemsUsed({
  choices,
  rows,
  onChange,
  defaultQty = "1",
  plans,
}: {
  /** `undefined` means not loaded yet (or failed to load) and renders nothing;
   *  only an explicit empty array says what is mapped is out of stock. */
  choices: StockChoice[] | undefined;
  rows: ItemRow[];
  onChange: (rows: ItemRow[]) => void;
  defaultQty?: string;
  /** What `event_batches` said, keyed by `planKey(item, store)`. Absent until it has answered;
   *  a plan for an item that is not batch tracked turns the picker into words. */
  plans?: Record<string, BatchPlan>;
}) {
  // Not known yet: say nothing. Claiming "nothing is mapped" while the list is
  // still loading, or after it failed, sends a correct farm to fix a mapping
  // that is not broken.
  if (!choices) return null;

  // `[]` means ONE thing: the event is mapped to item groups and nothing in
  // them is in stock. Not-mapped is an absent list (`undefined`, above), so a
  // farm that has configured everything is never sent to Settings to add a row
  // it already has.
  if (!choices.length)
    return (
      <Notice tone="info">
        Nothing mapped to this event is in stock right now, so it cannot use
        anything from the store.
      </Notice>
    );

  const where = new Map(choices.map((c) => [c.value, c]));

  function set(key: number, patch: Partial<ItemRow>) {
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  return (
    <div className="flex flex-col gap-3">
      {rows.map((r) => {
        const chosen = where.get(r.item);
        // A plan answers for one item in one store. Anything else is somebody
        // else's batches and must never render here.
        const found = plans?.[planKey(r.item, r.store)];
        const plan = found && found.warehouse === r.store ? found : undefined;
        return (
          <div key={r.key} className="grid gap-3 sm:grid-cols-[2fr_0.6fr_1.4fr_1.4fr_auto]">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`item-${r.key}`}>Item</Label>
              <Picker
                id={`item-${r.key}`}
                value={r.item}
                // Choosing the item chooses the store it is mostly in.
                onChange={(next) =>
                  set(r.key, { item: next, store: where.get(next)?.warehouse ?? "", batch: "" })
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
                onChange={(next) => set(r.key, { store: next, batch: "" })}
                options={(chosen?.locations ?? []).map((l) => ({
                  value: l.warehouse,
                  label: `${l.warehouse} · ${l.qty} ${chosen?.uom ?? ""}`.trim(),
                }))}
                label="From store"
                placeholder="—"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              {plan && <Label htmlFor={`batch-${r.key}`}>Batch</Label>}
              {plan?.tracked ? (
                <Picker
                  id={`batch-${r.key}`}
                  value={r.batch}
                  onChange={(next) => set(r.key, { batch: next })}
                  options={plan.available.map((b) => ({
                    value: b.batch_no,
                    label: `${b.batch_no} · ${b.qty} here${
                      b.expiry_date ? ` · expires ${b.expiry_date}` : ""
                    }`,
                  }))}
                  label="Batch"
                  placeholder="Chosen by the rule"
                />
              ) : plan ? (
                // Not batch tracked, so nothing will ever ask it for a batch.
                <span className="pt-2 text-[12px] text-[var(--sd-quiet)]">not batched</span>
              ) : null}
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
        <Button type="button" variant="outline" size="sm" onClick={() => onChange([...rows, blankRow(defaultQty)])}>
          Another item
        </Button>
      </div>
    </div>
  );
}
