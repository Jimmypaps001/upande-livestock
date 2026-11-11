import { useState, type Dispatch, type SetStateAction } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import {
  applyPercentages,
  kgFromPercent,
  kgTotal,
  percentTotal,
  withPercentages,
  type LineUnit,
} from "@/lib/ration-maths";
import { cn, fmt } from "@/lib/utils";

/** A recipe row the two editors share the shape of. */
export type ModeRow = { key: number; item_code: string; qty: string; pct?: string; unit?: LineUnit };

/**
 * Kilos per line, or kilos per head and a percentage per line.
 *
 * Mutara's ration sheet is written the second way: "Finishers, 18 kg a head:
 * silage 62.5%, maize germ 20%…". Percentage mode lets the editors take it
 * like that and still save kilogram lines, which is all a BOM holds — the
 * percentages are a way of typing, not something stored. Changing the kilos
 * per head rescales every line, so a group moved up to 20 kg keeps its mix.
 *
 * Doses (grams, millilitres a head) sit outside the 100% and never move.
 */
export function usePercentMode<T extends ModeRow>(rows: T[], setRows: Dispatch<SetStateAction<T[]>>) {
  const [on, setOn] = useState(false);
  const [kgPerHead, setKgPerHead] = useState("");

  function toggle(next: boolean) {
    if (next) {
      setKgPerHead(String(kgTotal(rows)));
      setRows((s) => withPercentages(s));
    }
    setOn(next);
  }

  /** New rows (a herd loaded, a recipe expanded) arrive in kilos. */
  function seed(next: T[]): T[] {
    if (!on) return next;
    setKgPerHead(String(kgTotal(next)));
    return withPercentages(next);
  }

  function changeKgPerHead(value: string) {
    setKgPerHead(value);
    setRows((s) => applyPercentages(s, value));
  }

  function changePct(key: number, value: string) {
    setRows((s) =>
      s.map((r) => (r.key === key ? { ...r, pct: value, qty: String(kgFromPercent(kgPerHead, value)) } : r)),
    );
  }

  return { on, toggle, seed, kgPerHead, changeKgPerHead, changePct, pctTotal: percentTotal(rows) };
}

export type PercentMode = ReturnType<typeof usePercentMode>;

/** The switch between kilos and percentages, and the kilos-per-head field. */
export function RecipeModeBar({
  mode,
  idPrefix,
  per = "head per day",
}: {
  mode: PercentMode;
  idPrefix: string;
  /** What the kilos are per: a head per day for a ration, a batch for a concentrate. */
  per?: string;
}) {
  const off100 = mode.on && Math.abs(mode.pctTotal - 100) > 0.01;
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label>Enter as</Label>
        <div className="inline-flex overflow-hidden rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
          {([false, true] as const).map((pct) => (
            <button
              key={String(pct)}
              type="button"
              onClick={() => mode.toggle(pct)}
              aria-pressed={mode.on === pct}
              className={cn(
                "px-3 py-1.5 text-[12.5px] font-medium",
                mode.on === pct ? "bg-[var(--sd-ink)] text-white" : "text-[var(--sd-muted)]",
              )}
            >
              {pct ? "% of intake" : "Kilos"}
            </button>
          ))}
        </div>
      </div>
      {mode.on && (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${idPrefix}-kg-per`}>Kg per {per}</Label>
            <Input
              id={`${idPrefix}-kg-per`}
              type="number"
              min={0}
              step="any"
              className="w-28 text-right tabular-nums"
              value={mode.kgPerHead}
              onChange={(e) => mode.changeKgPerHead(e.target.value)}
            />
          </div>
          <span
            className={cn(
              "pb-2 text-[12px] tabular-nums",
              off100 ? "text-[var(--sd-sev-critical)]" : "text-[var(--sd-muted)]",
            )}
          >
            {fmt(mode.pctTotal)}% allocated{off100 ? " — the lines should add up to 100%" : ""}
          </span>
        </>
      )}
    </div>
  );
}

const UNIT_OPTIONS = [
  { value: "kg", label: "kg" },
  { value: "Gram", label: "g a head" },
  { value: "Millilitre", label: "ml a head" },
];

/** Kilos, or a per-head dose in grams or millilitres outside the 100%. */
export function UnitPicker({
  id,
  value,
  onChange,
}: {
  id: string;
  value: LineUnit | undefined;
  onChange: (next: LineUnit) => void;
}) {
  return (
    <Picker
      id={id}
      value={value || "kg"}
      onChange={(v) => onChange((v || "kg") as LineUnit)}
      options={UNIT_OPTIONS}
      label="Unit"
      className="w-28"
    />
  );
}
