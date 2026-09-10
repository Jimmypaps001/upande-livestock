import { useEffect, useRef, useState } from "react";
import { Plus, X } from "lucide-react";
import { AmberNotice, Mark, Notice } from "@/components/feeding/Notice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { searchItems } from "@/lib/frappe";
import type { ManualRow } from "@/lib/feeding";
import { num, todayISO } from "@/lib/utils";

export const MANUAL_WARNING =
  "You are setting the recipe and the head count yourself. This moves real " +
  "stock out of the store — you are accountable for what you enter.";

/**
 * The herd's ration as the system would mix it, handed to the operator to
 * correct: the store did not have what the recipe called for, or the trough
 * did not have the herd's full head count in front of it.
 *
 * Every quantity here is PER HEAD, in the base BOM's recipe unit — the unit
 * the row was seeded in, shown beside each field. It is sent to the server in
 * exactly that unit. Nothing on this screen converts between recipe and stock
 * units: hay is written in kg on the herd BOM but stocked in BALE at 0.07
 * bale/kg, and a conversion here would issue roughly fourteen times the hay.
 */
export function ManualConfig({
  rows,
  onRowsChange,
  heads,
  onHeadsChange,
  date,
  onSubmit,
  busy,
  disabledReason,
}: {
  rows: ManualRow[] | null;
  onRowsChange: (next: ManualRow[]) => void;
  heads: string;
  onHeadsChange: (next: string) => void;
  /** The page's posting date, set by the Live/Backdate switch at the top.
   *  Read-only here — this form no longer carries a date of its own, so the
   *  two tabs cannot disagree about which day a run lands on. */
  date: string;
  onSubmit: () => void;
  busy: boolean;
  disabledReason: string | null;
}) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<
    Array<{ name: string; item_name: string; stock_uom: string }>
  >([]);
  const [addError, setAddError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(timer.current);
    const q = term.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }
    timer.current = window.setTimeout(() => {
      searchItems(q).then(setResults);
    }, 250);
    return () => window.clearTimeout(timer.current);
  }, [term]);

  function addIngredient() {
    setAddError(null);
    const code = term.trim();
    if (!code) {
      setAddError("Type an item to add.");
      return;
    }
    const current = rows || [];
    if (current.some((r) => r.item_code === code)) {
      setAddError("That ingredient is already in the list.");
      return;
    }
    const hit = results.find((it) => it.name === code) || results[0];
    if (!hit) {
      setAddError("Item not found.");
      return;
    }
    onRowsChange([
      ...current,
      // A hand-added ingredient has no BOM line, so its recipe unit is its
      // stock unit — the server reads the tuned BOM in that unit.
      { item_code: hit.name, item_name: hit.item_name, uom: hit.stock_uom, qty: 0 },
    ]);
    setTerm("");
    setResults([]);
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-2">
        <Mark>Manual</Mark>
        <span className="text-[12px] text-[var(--sd-muted)]">
          Posted as a manual run, through the same stock movement as the system path.
        </span>
      </div>

      <AmberNotice>{MANUAL_WARNING}</AmberNotice>

      {!rows || !rows.length ? (
        <Notice tone="info">Select a herd first.</Notice>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((r, i) => (
            <div
              key={r.item_code}
              className="flex items-center gap-3 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-card)] px-3 py-2.5"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                  {r.item_name || r.item_code}
                </div>
                <div className="text-[11px] text-[var(--sd-quiet)]">
                  {r.uom} per head
                </div>
              </div>
              <Input
                type="number"
                min={0}
                step="any"
                className="w-32 text-right tabular-nums"
                aria-label={`${r.item_name || r.item_code} per head, in ${r.uom}`}
                value={r.qty}
                onChange={(e) => {
                  const next = rows.slice();
                  next[i] = { ...r, qty: num(e.target.value) };
                  onRowsChange(next);
                }}
              />
              <button
                type="button"
                aria-label={`Remove ${r.item_name || r.item_code}`}
                onClick={() => onRowsChange(rows.filter((_, j) => j !== i))}
                className="rounded-md p-1.5 text-[var(--sd-quiet)] transition-colors hover:bg-[var(--sd-bg-soft)] hover:text-[var(--sd-ink)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-[16rem] flex-1 flex-col gap-1.5">
          <Label htmlFor="fm-item" className="text-[var(--sd-muted)]">
            Add an ingredient{" "}
            <span className="font-normal text-[var(--sd-quiet)]">
              — type to search the item master
            </span>
          </Label>
          <Input
            id="fm-item"
            list="livestock-fm-items"
            placeholder="Item name or code…"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
          />
          <datalist id="livestock-fm-items">
            {results.map((it) => (
              <option key={it.name} value={it.name}>
                {it.item_name}
              </option>
            ))}
          </datalist>
        </div>
        <Button type="button" variant="outline" onClick={addIngredient}>
          <Plus className="mr-1.5 h-4 w-4" />
          Add ingredient
        </Button>
      </div>
      {addError && <Notice tone="error">{addError}</Notice>}

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex w-40 flex-col gap-1.5">
          <Label htmlFor="fm-heads" className="text-[var(--sd-muted)]">
            Animals fed
          </Label>
          <Input
            id="fm-heads"
            type="number"
            min={1}
            step={1}
            value={heads}
            onChange={(e) => onHeadsChange(e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={onSubmit} disabled={busy || !!disabledReason}>
          {busy ? "Mixing…" : "Mix & feed"}
        </Button>
        {date !== todayISO() && <Mark>Backdated · {date}</Mark>}
        {disabledReason && (
          <span className="text-[12px] text-[var(--sd-quiet)]">{disabledReason}</span>
        )}
      </div>
    </div>
  );
}
