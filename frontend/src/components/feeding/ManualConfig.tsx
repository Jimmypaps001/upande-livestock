import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { AmberNotice, Mark, Notice } from "@/components/feeding/Notice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { isError, searchItems } from "@/lib/frappe";
import { feedSubstitutes, type ManualRow, type Substitute } from "@/lib/feeding";
import { isDoseUom, swapKg } from "@/lib/ration-maths";
import { isKg, kgPerUnit, storeUnits, useFeedUnits, type UnitsMap } from "@/lib/units";
import { fmt, num, todayISO } from "@/lib/utils";

/**
 * The units a manual line may be written in: kilos, the units the store counts
 * the item in (its stock unit and UOM conversions), and the line's own unit.
 * Kilos are offered under the name the item or line already uses ("Kg" on
 * live, "Kilogram" here), so the server matches it to the recipe's row.
 */
export function manualUnitOptions(units: UnitsMap, row: { item_code: string; uom: string }): string[] {
  const own = row.uom || "";
  const kgName = isKg(own)
    ? own
    : units[row.item_code]?.uoms.find((o) => isKg(o.uom))?.uom ||
      (isKg(units[row.item_code]?.stock_uom) ? units[row.item_code]!.stock_uom : "Kg");
  const out = [kgName, ...storeUnits(units, row.item_code).map((o) => o.uom)];
  if (own && !out.includes(own)) out.push(own);
  return out;
}

/** A manual line in another unit: the kilos stay and the quantity follows,
 *  when both units have a kilo figure; otherwise only the unit changes. */
export function changeManualUnit(units: UnitsMap, row: ManualRow, uom: string): ManualRow {
  const was = kgPerUnit(units, row.item_code, row.uom);
  const now = kgPerUnit(units, row.item_code, uom);
  const qty = was && now ? Math.round(((num(row.qty) * was) / now) * 10000) / 10000 : row.qty;
  return { ...row, uom, qty };
}

/**
 * A line swapped for another feed in its substitute group, kilos adjusted so
 * the herd gets the same dry matter. Pure, so the page and the tests agree.
 * Returns null when the swap cannot be balanced (no dry matter recorded).
 */
export function swapRow(row: ManualRow, sub: Substitute): ManualRow | null {
  const qty = swapKg(row.qty, sub.factor);
  if (qty == null) return null;
  return {
    item_code: sub.item_code,
    item_name: sub.item_name,
    // Weighed in kilos, whatever it is stocked in: the server converts a
    // line that names its unit (`_tuned_bom.row_units`).
    uom: row.uom,
    qty,
    swapped_from: row.swapped_from || row.item_name || row.item_code,
  };
}

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
 *
 * A line whose feed has a substitute group (`Livestock Feed.substitute_group`)
 * can be swapped for another in the group, its kilos adjusted by the server's
 * dry-matter factor. It is a change to today's mix only, posted as a tuned
 * recipe; the herd's ration is not touched.
 *
 * On a farm that does not feed by head count, `total` is the group's kilos as
 * weighed, and the per-head lines are scaled to it.
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
  byHeadCount = true,
  total = "",
  onTotalChange,
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
  /** Livestock Settings > Feed by Head Count. Off: `total` is typed. */
  byHeadCount?: boolean;
  total?: string;
  onTotalChange?: (next: string) => void;
}) {
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(false);
  // Unfiltered — the server's own matches for the typed term. What is
  // actually offered (`suggestions` below) still has to drop whatever is
  // already on this recipe, and that has to stay live: adding a row while
  // the panel is open must pull it out of the list without a new request.
  const [rawResults, setRawResults] = useState<
    Array<{ name: string; item_name: string; stock_uom: string }>
  >([]);
  const [searching, setSearching] = useState(false);
  const [subs, setSubs] = useState<Record<string, Substitute[]>>({});
  const units = useFeedUnits(useMemo(() => (rows || []).map((r) => r.item_code), [rows]));
  const timer = useRef<number | undefined>(undefined);

  // What each line could be swapped for. Asked again only when the set of
  // feeds on the recipe changes, not on every quantity typed.
  const itemsKey = (rows || []).map((r) => r.item_code).sort().join("|");
  useEffect(() => {
    if (!itemsKey) {
      setSubs({});
      return;
    }
    let live = true;
    feedSubstitutes(itemsKey.split("|")).then((r) => {
      if (live && !isError(r)) setSubs(r.substitutes || {});
    });
    return () => {
      live = false;
    };
  }, [itemsKey]);

  /** The swaps a line may take: weighed in kilos, balanced on dry matter, not already on the recipe. */
  function swapsFor(r: ManualRow): Substitute[] {
    if (!isKg(r.uom)) return [];
    return (subs[r.item_code] || []).filter((s) => s.factor && !already.has(s.item_code));
  }
  const box = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  // Debounced: a request per keystroke against the item master is wasteful,
  // so the server is asked only once typing pauses for 250ms.
  useEffect(() => {
    window.clearTimeout(timer.current);
    const q = term.trim();
    if (q.length < 2) {
      setRawResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    timer.current = window.setTimeout(() => {
      searchItems(q).then((found) => {
        setSearching(false);
        setRawResults(found);
      });
    }, 250);
    return () => window.clearTimeout(timer.current);
  }, [term]);

  // Never offer an item already on the recipe — a duplicate row is not
  // corrupted by `_tuned_bom._clean` (it sums same-item_code lines), but it
  // reads as broken to the operator, which is reason enough to keep it out
  // of the list rather than let it be picked twice.
  const already = useMemo(() => new Set((rows || []).map((r) => r.item_code)), [rows]);
  const suggestions = useMemo(
    () => rawResults.filter((it) => !already.has(it.name)),
    [rawResults, already],
  );

  function choose(item: { name: string; item_name: string; stock_uom: string }) {
    onRowsChange([
      ...(rows || []),
      // A hand-added ingredient has no BOM line, so its recipe unit is its
      // stock unit — the server reads the tuned BOM in that unit.
      { item_code: item.name, item_name: item.item_name, uom: item.stock_uom, qty: 0 },
    ]);
    setTerm("");
    setRawResults([]);
    setOpen(false);
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
                  {!isKg(r.uom) && !isDoseUom(r.uom) && kgPerUnit(units, r.item_code, r.uom)
                    ? ` ≈ ${fmt(num(r.qty) * kgPerUnit(units, r.item_code, r.uom)!)} kg`
                    : ""}
                  {r.swapped_from ? ` · swapped in for ${r.swapped_from}, same dry matter` : ""}
                </div>
              </div>
              {swapsFor(r).length > 0 && (
                <Picker
                  id={`fm-swap-${i}`}
                  value=""
                  onChange={(code) => {
                    const sub = swapsFor(r).find((s) => s.item_code === code);
                    const next = sub ? swapRow(r, sub) : null;
                    if (!next) return;
                    const out = rows.slice();
                    out[i] = next;
                    onRowsChange(out);
                  }}
                  options={swapsFor(r).map((s) => ({
                    value: s.item_code,
                    label: `${s.item_name} — ${fmt(swapKg(r.qty, s.factor) ?? 0)} ${r.uom}${
                      s.on_hand != null ? ` (${fmt(s.on_hand)} ${s.stock_uom || ""} in store)` : ""
                    }`,
                  }))}
                  label={`Swap ${r.item_name || r.item_code}`}
                  placeholder="Swap for…"
                  className="w-40"
                />
              )}
              {!isDoseUom(r.uom) && manualUnitOptions(units, r).length > 1 && (
                <Picker
                  id={`fm-unit-${i}`}
                  value={r.uom}
                  onChange={(uom) => {
                    if (!uom || uom === r.uom) return;
                    const next = rows.slice();
                    next[i] = changeManualUnit(units, r, uom);
                    onRowsChange(next);
                  }}
                  options={manualUnitOptions(units, r)}
                  label={`Unit for ${r.item_name || r.item_code}`}
                  className="w-28"
                />
              )}
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
        <div ref={box} className="relative flex min-w-[16rem] flex-1 flex-col gap-1.5">
          <Label htmlFor="fm-item" className="text-[var(--sd-muted)]">
            Add an ingredient{" "}
            <span className="font-normal text-[var(--sd-quiet)]">
              — type to search the item master
            </span>
          </Label>
          <Input
            id="fm-item"
            autoComplete="off"
            placeholder="Item name or code…"
            value={term}
            onFocus={() => setOpen(true)}
            onChange={(e) => {
              setTerm(e.target.value);
              setOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
            }}
          />
          {open && term.trim().length > 0 && (
            <div className="absolute top-full z-30 mt-1 w-full rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-card)] p-1.5 shadow-[0_12px_32px_-16px_rgba(10,10,10,0.4)]">
              {term.trim().length < 2 ? (
                <p className="px-2 py-2 text-[12px] text-[var(--sd-muted)]">
                  Keep typing — at least 2 characters.
                </p>
              ) : searching ? (
                <div className="flex items-center gap-2 px-2 py-2 text-[12px] text-[var(--sd-muted)]">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Searching…
                </div>
              ) : suggestions.length === 0 ? (
                <p className="px-2 py-2 text-[12px] text-[var(--sd-muted)]">
                  {rawResults.length > 0
                    ? "Every match is already on this recipe."
                    : `No item matches "${term.trim()}".`}
                </p>
              ) : (
                <div className="max-h-56 overflow-y-auto">
                  {suggestions.map((it) => (
                    <button
                      key={it.name}
                      type="button"
                      onClick={() => choose(it)}
                      className="flex w-full items-start gap-2 rounded-[var(--sd-radius)] px-2 py-1.5 text-left text-[13px] transition-colors hover:bg-[var(--sd-bg-soft)]"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-[var(--sd-ink)]">
                          {it.item_name || it.name}
                        </span>
                        <span className="block truncate text-[11px] text-[var(--sd-quiet)]">
                          {it.name} · {it.stock_uom}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

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
        {!byHeadCount && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="fm-total" className="text-[var(--sd-muted)]">
              Total fed (kg)
            </Label>
            <Input
              id="fm-total"
              type="number"
              min={0}
              step="any"
              className="w-36 text-right tabular-nums"
              value={total}
              onChange={(e) => onTotalChange?.(e.target.value)}
            />
            <span className="text-[11px] text-[var(--sd-quiet)]">
              Suggested{" "}
              {fmt(
                num(heads) *
                  (rows || []).reduce(
                    (s, r) => s + (isDoseUom(r.uom) ? 0 : num(r.qty) * (kgPerUnit(units, r.item_code, r.uom) ?? 0)),
                    0,
                  ),
              )}{" "}
              kg: head count &times; per head. What you type is what is mixed.
            </span>
          </div>
        )}
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
