import { useState, type Dispatch, type SetStateAction } from "react";
import { Lock, LockOpen } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import {
  changeTotal as totalChanged,
  editLine,
  hasDefiniteTotal,
  kgTotal,
  percentTotal,
  rebalance,
  sharesOf,
  toggleLock as lockToggled,
  unheld,
  type Balanced,
  type LineUnit,
} from "@/lib/ration-maths";
import { cn, fmt } from "@/lib/utils";

/** A recipe row the editors share the shape of. `kgPer` is kilos in one of
 *  `unit` when it is a store unit (Litre, BALE), so the sums run on kilos.
 *  `locked` is screen state: it is never saved. */
export type ModeRow = {
  key: number;
  item_code: string;
  qty: string;
  pct?: string;
  unit?: LineUnit;
  kgPer?: number | null;
  locked?: boolean;
};

/**
 * Kilos AND % of intake on every line, both editable, with locks.
 *
 * Mutara's ration sheet is written "Finishers, 18 kg a head: silage 62.5%,
 * maize germ 20%…", and the herdsman also thinks in kilos ("give them 8 kg
 * of silage"). So every weighed line takes either, and the kilos per head is
 * an optional total. The rule (typing locks a line against a definite total,
 * the unlocked lines take up the difference, a % with no total makes the sum
 * the total, changing the total keeps every %) is pure and lives in
 * `ration-maths.ts` (`editLine`, `changeTotal`, `rebalance`), where it is
 * tested; this only holds the total, the notice and the rows.
 *
 * What is saved is kilogram lines (or a store unit, or a dose), as before:
 * the percentages and the locks are a way of writing the recipe, not part of
 * it. Doses (g, ml a head) sit outside the 100% and outside the locks.
 */
export function useRecipeBalance<T extends ModeRow>(rows: T[], setRows: Dispatch<SetStateAction<T[]>>) {
  const [total, setTotal] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const definite = hasDefiniteTotal(total);

  function take(b: Balanced<T>) {
    setRows(b.rows);
    setTotal(b.total);
    setNotice(b.notice);
  }

  const at = (key: number) => rows.findIndex((r) => r.key === key);

  /** New rows (a herd loaded, a recipe expanded) arrive in kilos, with no total. */
  function seed(next: T[]): T[] {
    setTotal("");
    setNotice(null);
    return unheld(next);
  }

  // Each line's % as shown: the held figures against a total; worked out from
  // the kilos without one (a store unit's kilos can arrive after the rows).
  const shares = definite ? rows.map((r) => r.pct ?? "") : sharesOf(rows);

  return {
    total,
    definite,
    notice,
    /** What the lines weigh: the total when none is set. */
    sum: kgTotal(rows),
    shares,
    pctTotal: percentTotal(rows.map((r, i) => ({ unit: r.unit, pct: shares[i] }))),
    seed,
    editQty: (key: number, value: string) => take(editLine(rows, total, at(key), "qty", value)),
    editPct: (key: number, value: string) => take(editLine(rows, total, at(key), "pct", value)),
    changeTotal: (value: string) => take(totalChanged(rows, total, value)),
    toggleLock: (key: number) => setRows(lockToggled(rows, at(key), total)),
    /** After a line is added, taken out, merged or put in another unit. */
    settle: (next: T[]) => take(rebalance(next, total)),
  };
}

export type RecipeBalance = ReturnType<typeof useRecipeBalance>;

/** The kilos-per-head total, what is allocated, and why a figure was held back. */
export function RecipeTotalBar({
  mode,
  idPrefix,
  per = "head per day",
}: {
  mode: RecipeBalance;
  idPrefix: string;
  /** What the kilos are per: a head per day for a ration, a batch for a concentrate. */
  per?: string;
}) {
  const off100 = mode.definite && Math.abs(mode.pctTotal - 100) > 0.01;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${idPrefix}-kg-per`}>Kg per {per}</Label>
          <Input
            id={`${idPrefix}-kg-per`}
            type="number"
            min={0}
            step="any"
            className="w-28 text-right tabular-nums"
            value={mode.total}
            placeholder={mode.sum ? String(mode.sum) : "optional"}
            onChange={(e) => mode.changeTotal(e.target.value)}
          />
        </div>
        <span
          className={cn(
            "pb-2 text-[12px] tabular-nums",
            off100 ? "text-[var(--sd-sev-critical)]" : "text-[var(--sd-muted)]",
          )}
        >
          {mode.definite
            ? `${fmt(mode.pctTotal)}% allocated${off100 ? " — the lines should add up to 100%" : ""}. Typing a line's kilos or % locks it; the unlocked lines make up the rest.`
            : "No total set: the lines add up to whatever they come to. Type a total (or any line's %) to hold the recipe to it."}
        </span>
      </div>
      {mode.notice && (
        <p role="status" className="text-[12px] text-[var(--sd-sev-warning,#b45309)]">
          {mode.notice}
        </p>
      )}
    </div>
  );
}

/** A line's lock: shown against a definite total, click to lock or unlock. */
export function LockButton({
  locked,
  label,
  onClick,
}: {
  locked: boolean;
  /** The feed's name, for the button's accessible name. */
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={locked}
      aria-label={`${locked ? "Unlock" : "Lock"} ${label}`}
      title={locked ? "Locked: other lines move around it. Click to unlock." : "Unlocked: takes up changes elsewhere. Click to lock."}
      className={cn(
        "mb-2 transition-colors",
        locked ? "text-[var(--sd-ink)]" : "text-[var(--sd-quiet)] hover:text-[var(--sd-ink)]",
      )}
    >
      {locked ? <Lock className="h-4 w-4" /> : <LockOpen className="h-4 w-4" />}
    </button>
  );
}

/**
 * Kilos, a unit the store counts the item in (its stock unit and its UOM
 * conversions: Litre, BALE…), or a per-head dose in grams or millilitres
 * outside the 100%.
 */
export function UnitPicker({
  id,
  value,
  onChange,
  storeUnits = [],
}: {
  id: string;
  value: LineUnit | undefined;
  onChange: (next: LineUnit) => void;
  /** The item's units other than kilos and doses. */
  storeUnits?: string[];
}) {
  const current = value || "kg";
  const extra = [...storeUnits];
  // A line already written in a unit the item no longer lists keeps it.
  if (current !== "kg" && current !== "Gram" && current !== "Millilitre" && !extra.includes(current)) {
    extra.push(current);
  }
  return (
    <Picker
      id={id}
      value={current}
      onChange={(v) => onChange((v || "kg") as LineUnit)}
      options={[
        { value: "kg", label: "kg" },
        ...extra.map((u) => ({ value: u, label: u })),
        { value: "Gram", label: "g a head" },
        { value: "Millilitre", label: "ml a head" },
      ]}
      label="Unit"
      className="w-28"
    />
  );
}
