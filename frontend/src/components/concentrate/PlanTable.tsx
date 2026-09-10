import { Notice, Pill } from "@/components/feeding/Notice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ConcentrateWeeklyPlan, ConcentrateWeeklyRow } from "@/lib/feeding";
import { fmt } from "@/lib/utils";

/**
 * The batches to put through the mixer, one row per concentrate.
 *
 * The farm mixes weekly and feeds twice a day out of the store, so this is a
 * list of batches to run rather than a per-herd figure. `can_mix` matters as
 * much as the quantity: a plan reading "mix 6.3 tonnes" while the store has no
 * canola looks like a decision has been made when it has not — so the Run
 * column is disabled whenever `can_mix` is false, and the "Can mix" badge
 * already names what is short. The quantity defaults to `to_mix_kg` (already
 * rounded up to whole batches) but is the operator's to change: a mixer
 * sometimes runs a different number of batches than the plan suggests.
 */
export function PlanTable({
  plan,
  error,
  qtyByItem,
  onQtyChange,
  onMix,
  mixingItem,
}: {
  plan: ConcentrateWeeklyPlan | null;
  error: string | null;
  qtyByItem: Record<string, string>;
  onQtyChange: (itemCode: string, value: string) => void;
  onMix: (row: ConcentrateWeeklyRow) => void;
  mixingItem: string | null;
}) {
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!plan) return null;
  if (!plan.concentrates.length)
    return <Notice tone="info">No herd ration draws on a concentrate.</Notice>;

  return (
    <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
      <table className="w-full min-w-[64rem] text-[13px]">
        <thead>
          <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
            <th className="px-3 py-2.5 font-medium">Concentrate</th>
            <th className="px-3 py-2.5 text-right font-medium">Per day</th>
            <th className="px-3 py-2.5 text-right font-medium">Needs</th>
            <th className="px-3 py-2.5 text-right font-medium">In store</th>
            <th className="px-3 py-2.5 text-right font-medium">Cover</th>
            <th className="px-3 py-2.5 text-right font-medium">To mix</th>
            <th className="px-3 py-2.5 text-right font-medium">Batches</th>
            <th className="px-3 py-2.5 font-medium">Can mix</th>
            <th className="px-3 py-2.5 text-right font-medium">Run</th>
          </tr>
        </thead>
        <tbody>
          {plan.concentrates.map((c) => {
            const busy = mixingItem === c.item_code;
            const blocked = mixingItem !== null;
            return (
              <tr key={c.item_code} className="border-b border-[var(--sd-line-soft)] last:border-0">
                <td className="px-3 py-2.5 font-medium text-[var(--sd-ink)]">{c.item_name}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmt(c.per_day_kg)} kg</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmt(c.needed_kg)} kg</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmt(c.on_hand_kg)} kg</td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {c.days_cover == null ? "—" : `${c.days_cover} d`}
                </td>
                <td className="px-3 py-2.5 text-right font-semibold tabular-nums text-[var(--sd-ink)]">
                  {fmt(c.to_mix_kg)} kg
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {c.batches > 0 ? (
                    <>
                      {c.batches}
                      <div className="text-[11px] text-[var(--sd-quiet)]">
                        × {fmt(plan.batch_kg)} kg
                      </div>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-3 py-2.5">
                  {c.to_mix_kg <= 0 ? (
                    <Pill tone="mute">Nothing to mix</Pill>
                  ) : c.can_mix ? (
                    <Pill tone="ok">Yes</Pill>
                  ) : (
                    <Pill tone="short">
                      Short: {c.short.map((s) => s.item_name || s.item_code).join(", ")}
                    </Pill>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  {c.to_mix_kg <= 0 ? (
                    <span className="block text-right text-[12px] text-[var(--sd-quiet)]">
                      Nothing to run
                    </span>
                  ) : (
                    <div className="flex items-center justify-end gap-2">
                      <Input
                        type="number"
                        min={0}
                        step="any"
                        aria-label={`Quantity to mix for ${c.item_name}`}
                        className="h-8 w-24 text-right tabular-nums"
                        value={qtyByItem[c.item_code] ?? String(c.to_mix_kg)}
                        onChange={(e) => onQtyChange(c.item_code, e.target.value)}
                        disabled={!c.can_mix || busy || blocked}
                      />
                      <Button
                        size="sm"
                        onClick={() => onMix(c)}
                        disabled={!c.can_mix || blocked}
                      >
                        {busy ? "Mixing…" : "Mix"}
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
