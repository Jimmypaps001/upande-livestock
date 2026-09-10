import { Mark } from "@/components/feeding/Notice";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Recipe } from "@/lib/feeding";
import { fmt } from "@/lib/utils";

/** "4 Sep 2026" from the `created` timestamp `herd_recipes` returns
 *  (`YYYY-MM-DD HH:MM:SS.ffffff`). Falls back to the raw string rather than
 *  hiding a recipe the date parse can't make sense of. */
function createdLabel(created: string): string {
  const d = new Date(created.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return created;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** What the picker shows for one recipe: the standing ration is labelled as
 *  such — it is the herd's normal ration, not just the first item in a list —
 *  and a tuned one carries the item name plus when it was made, which is
 *  enough to tell two tunes of the same item apart. */
export function recipeLabel(recipe: Recipe): string {
  return recipe.is_standing
    ? `${recipe.item_name} — standing ration`
    : `${recipe.item_name} — tuned ${createdLabel(recipe.created)}`;
}

/**
 * The herd's standing ration, plus every recipe tuned for it before.
 *
 * One picker, rendered on both the System tab and the Manual configuration
 * tab against the same `value`/`onChange` — so choosing a recipe on either
 * tab is the same choice on both, per the brief ("should also mirror on the
 * manual configuration"). The caller owns the re-seed-with-confirmation
 * decision; this component only reports what was picked.
 */
export function RecipePicker({
  recipes,
  value,
  onChange,
  idPrefix,
  disabled,
}: {
  recipes: Recipe[];
  value: string;
  onChange: (bomNo: string) => void;
  idPrefix: string;
  disabled?: boolean;
}) {
  if (!recipes.length) return null;
  const selected = recipes.find((r) => r.bom_no === value);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex w-full max-w-sm flex-col gap-1.5">
        <Label htmlFor={`${idPrefix}-recipe`} className="text-[var(--sd-muted)]">
          Recipe
        </Label>
        <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger id={`${idPrefix}-recipe`}>
            <SelectValue placeholder="Select recipe…" />
          </SelectTrigger>
          <SelectContent>
            {recipes.map((r) => (
              <SelectItem key={r.bom_no} value={r.bom_no}>
                {recipeLabel(r)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {selected && (
        <div className="flex flex-col gap-1.5 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-bg-soft)] px-3 py-2.5">
          <div className="flex items-center gap-2">
            {selected.is_standing ? (
              <Mark>Standing</Mark>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] border border-[var(--sd-line)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--sd-muted)]">
                Tuned
              </span>
            )}
            <span className="text-[11px] text-[var(--sd-quiet)]">
              {selected.is_standing
                ? "This herd's normal ration."
                : `Made ${createdLabel(selected.created)}.`}
            </span>
          </div>
          <div className="text-[12px] text-[var(--sd-muted)]">
            {selected.lines.map((ln) => `${ln.item_name} ${fmt(ln.qty)} ${ln.uom}`).join(" · ")}
          </div>
        </div>
      )}
    </div>
  );
}
