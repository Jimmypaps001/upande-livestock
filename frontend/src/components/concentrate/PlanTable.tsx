import { Notice, Pill } from "@/components/feeding/Notice";
import type { ConcentrateWeeklyPlan } from "@/lib/feeding";
import { fmt } from "@/lib/utils";

/**
 * The batches to put through the mixer, one row per concentrate.
 *
 * The farm mixes weekly and feeds twice a day out of the store, so this is a
 * list of batches to run rather than a per-herd figure. `can_mix` matters as
 * much as the quantity: a plan reading "mix 6.3 tonnes" while the store has no
 * canola looks like a decision has been made when it has not.
 *
 * Read-only, deliberately. Mixing a batch still happens on the desk block,
 * which stays live beside this page; a button here that did nothing would be
 * worse than no button.
 */
export function PlanTable({
  plan,
  error,
}: {
  plan: ConcentrateWeeklyPlan | null;
  error: string | null;
}) {
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!plan) return null;
  if (!plan.concentrates.length)
    return <Notice tone="info">No herd ration draws on a concentrate.</Notice>;

  return (
    <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
      <table className="w-full min-w-[52rem] text-[13px]">
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
          </tr>
        </thead>
        <tbody>
          {plan.concentrates.map((c) => (
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
