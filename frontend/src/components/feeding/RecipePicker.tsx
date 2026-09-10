import { AlertTriangle } from "lucide-react";
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

/** A recipe's per-head amount differs sharply enough from what this herd is
 *  typically fed that treating the two as interchangeable would be a real
 *  feeding error — more than double, or less than half the reference. `-010`
 *  (1.0 kg against its siblings' 12.3) is exactly this: about a twelfth of
 *  the herd's usual amount. */
const OUTLIER_RATIO = 2;

/** The median per-head amount across every recipe the picker offers for this
 *  herd — the reference `isOutlier` compares against.
 *
 *  NOT simply the standing ration's own figure: on the live site, INCALF
 *  HEIFERS' *currently linked* standing BOM (`-012`) itself carries
 *  `per_head_qty` 1.0 — the same mis-set figure as `-010` — while the five
 *  other recipes actually run against this herd (47 Work Orders between
 *  them) all carry 12.3. Anchoring the comparison to "whichever BOM happens
 *  to be standing today" would miss `-010` entirely here (it agrees with
 *  standing) and instead flag the herd's five most-used recipes as the odd
 *  ones out. The median of the whole offered set finds the herd's true
 *  typical amount regardless of which single BOM is currently linked, and
 *  will flag the standing entry itself if that is the one that has drifted —
 *  which, per this herd's real data, it is. */
function typicalPerHead(recipes: Recipe[]): number {
  const qtys = recipes.map((r) => Number(r.per_head_qty) || 0).filter((q) => q > 0);
  if (!qtys.length) return 0;
  const sorted = [...qtys].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** "4 Sep 2026" from a timestamp `herd_recipes` returns for either `created`
 *  or `last_fed` (`YYYY-MM-DD HH:MM:SS[.ffffff]`, or a bare date for
 *  `last_fed`). Falls back to the raw string rather than hiding a recipe the
 *  date parse can't make sense of. */
function dateLabel(raw: string): string {
  if (!raw) return "";
  const d = new Date(raw.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** `kind`, rendered sensibly for all three values `herd_recipes` can send —
 *  "Standing", "Tuned", and "Previous" (a recipe genuinely fed before but
 *  never a hand-tune). Never falls through to a blank or "undefined" label
 *  for a value this component doesn't recognise. */
function kindText(recipe: Recipe): string {
  switch (recipe.kind) {
    case "Standing":
      return "Standing ration";
    case "Tuned":
      return "Tuned";
    case "Previous":
      return "Previously fed";
    default:
      return recipe.kind || "Recipe";
  }
}

/** How many times this herd was actually mixed on this recipe, and when —
 *  the only two facts (per herd_recipes.py's module docstring) that tell one
 *  historical recipe from another in a dropdown. "Never fed" for a tune
 *  minted but not yet run. */
function usageText(recipe: Recipe): string {
  if (!recipe.times_fed) return "Never fed";
  const times = `Fed ${recipe.times_fed}×`;
  return recipe.last_fed ? `${times} · last ${dateLabel(recipe.last_fed)}` : times;
}

/** `${qty} ${uom} / head`, straight off the recipe. `per_head_qty` already
 *  IS the per-head figure in the recipe's own uom (see feeding.ts's `Recipe`
 *  docstring) — never converted, never derived. This is the number that
 *  tells `-010` apart from its siblings before either is ever mixed. */
function perHeadText(recipe: Recipe): string {
  return `${fmt(recipe.per_head_qty)} ${recipe.uom} / head`;
}

/** True when `recipe`'s per-head amount is more than double, or less than
 *  half, `referencePerHead` (the herd's typical amount — see
 *  `typicalPerHead`) — see `OUTLIER_RATIO`. Can fire on the standing entry:
 *  see `typicalPerHead`'s docstring for why that is deliberate. */
function isOutlier(recipe: Recipe, referencePerHead: number): boolean {
  if (!(referencePerHead > 0)) return false;
  const ratio = recipe.per_head_qty / referencePerHead;
  return !Number.isFinite(ratio) || ratio <= 1 / OUTLIER_RATIO || ratio >= OUTLIER_RATIO;
}

/** What the picker shows for one recipe in running text — the confirm
 *  dialog when switching, and the "selected" detail strip below the list.
 *  Standing reads as the herd's normal ration; a tune carries when it was
 *  made; a recipe that is neither reads as what it is — genuinely fed
 *  before, but never a hand-tune — rather than being mislabelled "tuned" for
 *  lack of a better word. */
export function recipeLabel(recipe: Recipe): string {
  if (recipe.is_standing) return `${recipe.item_name} — standing ration`;
  if (recipe.kind === "Tuned") return `${recipe.item_name} — tuned ${dateLabel(recipe.created)}`;
  return `${recipe.item_name} — previously fed`;
}

/**
 * The herd's standing ration, plus every recipe tuned for it or fed to it
 * before.
 *
 * One picker, rendered on both the System tab and the Manual configuration
 * tab against the same `value`/`onChange` — so choosing a recipe on either
 * tab is the same choice on both, per the brief ("should also mirror on the
 * manual configuration"). The caller owns the re-seed-with-confirmation
 * decision; this component only reports what was picked.
 *
 * Every option shows its own per-head figure — never just a name — because
 * these recipes are not interchangeable: one BOM can carry a per-head amount
 * a twelfth of its siblings' with nothing else on screen to say so. One that
 * differs sharply from what the herd is typically fed is flagged rather than
 * merely listed alongside the rest — see `typicalPerHead`'s docstring for why
 * that reference is the herd's median, not simply whichever BOM happens to
 * be linked as standing today.
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
  const referencePerHead = typicalPerHead(recipes);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex w-full max-w-sm flex-col gap-1.5">
        <Label htmlFor={`${idPrefix}-recipe`} className="text-[var(--sd-muted)]">
          Recipe
        </Label>
        <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger id={`${idPrefix}-recipe`}>
            {/* Radix mirrors the selected item's full multi-line content into
                the trigger unless SelectValue is given its own children — so
                the closed control gets a compact one-line summary while the
                open list (below) carries the fuller per-recipe detail. */}
            <SelectValue placeholder="Select recipe…">
              {selected ? `${recipeLabel(selected)} · ${perHeadText(selected)}` : undefined}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {recipes.map((r) => {
              const outlier = isOutlier(r, referencePerHead);
              return (
                <SelectItem key={r.bom_no} value={r.bom_no}>
                  <div className="flex flex-col gap-0.5 py-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{r.item_name}</span>
                      <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--sd-muted)]">
                        {kindText(r)}
                      </span>
                    </div>
                    <div
                      className={
                        "flex items-center gap-1 text-[11px] tabular-nums " +
                        (outlier
                          ? "font-semibold text-[var(--sd-sev-critical)]"
                          : "text-[var(--sd-muted)]")
                      }
                    >
                      {outlier && <AlertTriangle className="h-3 w-3 shrink-0" />}
                      <span>{perHeadText(r)}</span>
                      {outlier && <span>— far from what this herd is usually fed</span>}
                    </div>
                    <div className="text-[11px] text-[var(--sd-quiet)]">{usageText(r)}</div>
                  </div>
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </div>

      {selected && (
        <div className="flex flex-col gap-1.5 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-bg-soft)] px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            {selected.is_standing ? (
              <Mark>Standing</Mark>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] border border-[var(--sd-line)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--sd-muted)]">
                {kindText(selected)}
              </span>
            )}
            <span className="text-[11px] text-[var(--sd-quiet)]">
              {selected.is_standing
                ? "This herd's normal ration."
                : selected.kind === "Tuned"
                  ? `Made ${dateLabel(selected.created)}.`
                  : "Fed to this herd before, but never a hand-tune."}
            </span>
            <span className="text-[11px] font-semibold tabular-nums text-[var(--sd-ink)]">
              {perHeadText(selected)}
            </span>
            <span className="text-[11px] text-[var(--sd-quiet)]">{usageText(selected)}</span>
            {isOutlier(selected, referencePerHead) && (
              <span className="inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] bg-[rgba(196,48,43,0.09)] px-2 py-0.5 text-[10px] font-semibold text-[var(--sd-sev-critical)]">
                <AlertTriangle className="h-3 w-3" />
                Differs sharply from what this herd is usually fed per head
              </span>
            )}
          </div>
          <div className="text-[12px] text-[var(--sd-muted)]">
            {selected.lines.map((ln) => `${ln.item_name} ${fmt(ln.qty)} ${ln.uom}`).join(" · ")}
          </div>
        </div>
      )}
    </div>
  );
}
