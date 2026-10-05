import { Plus, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Picker } from "@/components/ui/picker";
import { SearchPicker } from "@/components/ui/search-picker";
import { Notice } from "@/components/feeding/Notice";
import type { StockChoice } from "@/lib/events";
import type { BatchPlan } from "@/lib/feeding";
import { planKey } from "@/lib/use-batch-plans";
import { cn } from "@/lib/utils";

/**
 * What a record used, out of the stores that actually hold it — as a grid of
 * rows the way a Stock Entry's items are: one header, one line per item.
 *
 * Any page whose event posts stock imports this; the choices are the event
 * type's in-stock items, which come with the page's options, so the item
 * search is a filter in the browser.
 *
 * The store is not configured here. Each choice carries the warehouse holding
 * the most of it (the event type's default store first, when it holds any)
 * and every warehouse holding any, so picking an item picks a store, and the
 * operator can move it to another that genuinely has stock.
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

// No. | Item | Qty | UOM | From store | Batch | ×
const COLUMNS = "grid-cols-[2.25rem_minmax(14rem,2.4fr)_5.5rem_4.5rem_minmax(11rem,1.5fr)_minmax(9rem,1.2fr)_2.5rem]";
const HEAD = "px-2 py-2 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--sd-quiet)]";
const CELL = "flex items-center border-l border-[var(--sd-line)] px-1 py-1";
// Controls sit flush in their cell, the way a grid's cells do.
const FLUSH = "h-8 border-0 bg-transparent shadow-none focus-visible:ring-1";

export function StockPicker({
  choices,
  rows,
  onChange,
  defaultQty = "1",
  plans,
  mapped = true,
}: {
  /** `undefined` means not loaded yet (or failed to load) and renders nothing;
   *  an explicit empty array is "nothing to offer" (see `mapped`). */
  choices: StockChoice[] | undefined;
  rows: ItemRow[];
  onChange: (rows: ItemRow[]) => void;
  defaultQty?: string;
  /** What `event_batches` said, keyed by `planKey(item, store)`. Absent until it has answered;
   *  a plan for an item that is not batch tracked turns the picker into words. */
  plans?: Record<string, BatchPlan>;
  /** Only read when `choices` is `[]`, which alone cannot say why. `false`:
   *  the event is not set to post stock (point it at Settings). Otherwise it
   *  is, and none of its items is in stock. */
  mapped?: boolean;
}) {
  // Not known yet: say nothing. Claiming "not set to post stock" while the
  // list is still loading, or after it failed, sends a correct farm to fix a
  // setting that is not broken.
  if (!choices) return null;

  if (!choices.length)
    return mapped ? (
      <Notice tone="info">
        Nothing mapped to this event is in stock right now, so it cannot use
        anything from the store.
      </Notice>
    ) : (
      <Notice tone="info">
        This event is not set to post stock, so it cannot use anything from the
        store. Set that in Settings &rarr; Stock.
      </Notice>
    );

  const where = new Map(choices.map((c) => [c.value, c]));
  const options = choices.map((c) => ({ value: c.value, label: c.label, short: c.item_name || undefined }));

  function set(key: number, patch: Partial<ItemRow>) {
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  // The last row is cleared rather than removed: the grid always has a line
  // to type into.
  function drop(key: number) {
    onChange(rows.length === 1 ? [blankRow(defaultQty)] : rows.filter((r) => r.key !== key));
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto rounded-md border border-[var(--sd-line)]">
        <div role="table" aria-label="Items used" className="min-w-[46rem]">
          <div role="row" className={cn("grid bg-[var(--sd-bg-soft)]", COLUMNS)}>
            <span role="columnheader" className={cn(HEAD, "text-center")}>No.</span>
            <span role="columnheader" className={HEAD}>Item</span>
            <span role="columnheader" className={cn(HEAD, "text-right")}>Qty</span>
            <span role="columnheader" className={HEAD}>UOM</span>
            <span role="columnheader" className={HEAD}>From store</span>
            <span role="columnheader" className={HEAD}>Batch</span>
            <span role="columnheader" className={HEAD}><span className="sr-only">Remove</span></span>
          </div>
          {rows.map((r, i) => {
            const chosen = where.get(r.item);
            // A plan answers for one item in one store. Anything else is
            // somebody else's batches and must never render here.
            const found = plans?.[planKey(r.item, r.store)];
            const plan = found && found.warehouse === r.store ? found : undefined;
            return (
              <div
                role="row"
                key={r.key}
                className={cn("grid border-t border-[var(--sd-line)] bg-[var(--sd-bg)]", COLUMNS)}
              >
                <span role="cell" className="flex items-center justify-center text-[12px] text-[var(--sd-quiet)] tabular-nums">
                  {i + 1}
                </span>
                <div role="cell" className={CELL}>
                  <SearchPicker
                    id={`item-${r.key}`}
                    value={r.item}
                    onChange={(next) =>
                      set(r.key, { item: next, store: where.get(next)?.warehouse ?? "", batch: "" })
                    }
                    options={options}
                    label="Item"
                    placeholder="Search the store…"
                    className={FLUSH}
                  />
                </div>
                <div role="cell" className={CELL}>
                  <Input
                    id={`qty-${r.key}`}
                    aria-label="Qty"
                    type="number"
                    min={0}
                    step="any"
                    value={r.qty}
                    onChange={(e) => set(r.key, { qty: e.target.value })}
                    className={cn(FLUSH, "text-right tabular-nums")}
                  />
                </div>
                <span role="cell" className={cn(CELL, "px-2 text-[12.5px] text-[var(--sd-muted)]")}>
                  {chosen?.uom ?? ""}
                </span>
                <div role="cell" className={CELL}>
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
                    className={FLUSH}
                  />
                </div>
                <div role="cell" className={CELL}>
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
                      className={FLUSH}
                    />
                  ) : plan ? (
                    // Not batch tracked, so nothing will ever ask it for a batch.
                    <span className="px-2 text-[12px] text-[var(--sd-quiet)]">not batched</span>
                  ) : null}
                </div>
                <div role="cell" className="flex items-center justify-center border-l border-[var(--sd-line)]">
                  <button
                    type="button"
                    aria-label={`Remove row ${i + 1}`}
                    title="Remove"
                    onClick={() => drop(r.key)}
                    className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--sd-quiet)] hover:bg-[var(--sd-bg-soft)] hover:text-[var(--sd-ink)]"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange([...rows, blankRow(defaultQty)])}
        >
          <Plus /> Add item
        </Button>
      </div>
    </div>
  );
}
