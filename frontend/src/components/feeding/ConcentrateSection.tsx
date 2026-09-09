import { Notice, Pill } from "@/components/feeding/Notice";
import { RequirementTable } from "@/components/feeding/RequirementTable";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ConcentratePlanCard, ConcentrateWeeklyPlan } from "@/lib/feeding";
import { fmt } from "@/lib/utils";

/**
 * The concentrates this herd's ration draws on.
 *
 * A concentrate is a raw material to the TMR and Work Orders run single-level,
 * so a short concentrate has to be mixed before the TMR run can go — which is
 * why it gets its own card rather than a line in the table above.
 *
 * Read-only in this slice: mixing a batch still happens on the desk block,
 * which stays live beside this page. Showing a button that did nothing would
 * be worse than showing none.
 */
export function ConcentrateCards({ cards }: { cards: ConcentratePlanCard[] }) {
  if (!cards?.length) return null;
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--sd-quiet)]">
        Concentrate
      </h2>
      <div className="grid gap-4 lg:grid-cols-2">
        {cards.map((c) => (
          <Card key={c.item_code}>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2 text-[15px]">
                {c.item_name}
                <Pill tone="mute">{c.source}</Pill>
              </CardTitle>
              <CardDescription>
                {c.source === "Bought in"
                  ? "Bought ready-packed — restock by purchase, not by a Work Order."
                  : c.needed
                    ? `The TMR run is short ${fmt(c.short_qty)} ${c.uom}. Batches are ${fmt(
                        c.batch_qty,
                      )} ${c.uom}, so ${c.batches} covers it.`
                    : `In stock — ${fmt(c.available)} ${c.uom} at ${
                        c.source_warehouse || "—"
                      }. One batch shown for reference.`}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {c.source === "Bought in" ? (
                c.needed ? (
                  <Pill tone="short">
                    Short {fmt(c.short_qty)} {c.uom} for this run
                  </Pill>
                ) : (
                  <Pill tone="ok">Enough in store for this run</Pill>
                )
              ) : c.needed ? (
                c.can_manufacture ? (
                  <Pill tone="ok">Enough stock to mix {c.item_name}</Pill>
                ) : (
                  <Pill tone="short">
                    Short: {c.shortages.map((l) => l.item_name).join(", ")}
                  </Pill>
                )
              ) : c.can_manufacture ? (
                <Pill tone="mute">Not needed for this run — a batch could be made anyway</Pill>
              ) : (
                <Pill tone="mute">
                  Not needed for this run. A further batch would be short:{" "}
                  {c.shortages.map((l) => l.item_name).join(", ")}
                </Pill>
              )}
              <RequirementTable lines={c.source === "Bought in" ? [] : c.lines} />
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

/**
 * The farm mixes concentrate weekly and feeds twice a day out of the store, so
 * this is a list of batches to run rather than a per-herd figure. `can_mix`
 * matters as much as the quantity: a plan reading "mix 6.3 tonnes" while the
 * store has no canola looks like a decision has been made when it has not.
 */
export function ConcentrateWeekly({
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
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
            <th className="px-3 py-2.5 font-medium">Concentrate</th>
            <th className="px-3 py-2.5 text-right font-medium">Per day</th>
            <th className="px-3 py-2.5 text-right font-medium">Needs</th>
            <th className="px-3 py-2.5 text-right font-medium">In store</th>
            <th className="px-3 py-2.5 text-right font-medium">Cover</th>
            <th className="px-3 py-2.5 text-right font-medium">To mix</th>
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
              <td className="px-3 py-2.5 text-right tabular-nums">
                {fmt(c.to_mix_kg)} kg
                {c.batches > 0 && (
                  <div className="text-[11px] text-[var(--sd-quiet)]">
                    {c.batches} × {fmt(plan.batch_kg)} kg
                  </div>
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
