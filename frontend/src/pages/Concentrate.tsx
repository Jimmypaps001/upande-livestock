import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { PlanTable } from "@/components/concentrate/PlanTable";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice, Pill } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isError } from "@/lib/frappe";
import { concentratePlan, type ConcentrateWeeklyPlan } from "@/lib/feeding";
import { fmt, num } from "@/lib/utils";

/**
 * Concentrate: what the farm holds and what it must mix.
 *
 * Its own surface rather than a section on the feeding page, because it is a
 * different question asked by a different person on a different day — the
 * feeder asks "what goes in this trough now", the store keeper asks "what do I
 * put through the mixer to get to next Monday".
 *
 * Demand is read off the herds — every ration's concentrate line times its head
 * count — so nothing is typed in and a herd that grows moves the plan on its
 * own.
 *
 * Mixing is NOT wired here on purpose. `manufacture_concentrate` stays on the
 * desk block, which is live beside this page; this slice is read-only until
 * that is asked for.
 */
export function Concentrate() {
  const [days, setDays] = useState("7");
  const [plan, setPlan] = useState<ConcentrateWeeklyPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (span: number) => {
    setLoading(true);
    const r = await concentratePlan(span);
    setLoading(false);
    if (isError(r)) {
      setPlan(null);
      setError(r.error);
      return;
    }
    setError(null);
    setPlan(r);
  }, []);

  useEffect(() => {
    load(7);
  }, [load]);

  const shortRows = (plan?.concentrates || []).filter(
    (c) => c.to_mix_kg > 0 && !c.can_mix,
  );

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Feeding" title="Concentrate">
        How much of each concentrate the herds will eat over the days you set, what the
        stores already hold, and how many whole batches close the gap. Mixing a batch is
        still done from the desk block.
      </PageHeading>

      <Card>
        <CardHeader className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <CardTitle>Cover</CardTitle>
            <CardDescription>
              Batches are whole: the recipes are stated per {plan ? fmt(plan.batch_kg) : "1,000"} kg
              and a mixer does not run a fifth of a batch on purpose.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex w-32 flex-col gap-1.5">
              <Label htmlFor="cp-days" className="text-[var(--sd-muted)]">
                Days
              </Label>
              <Input
                id="cp-days"
                type="number"
                min={1}
                max={60}
                step={1}
                value={days}
                onChange={(e) => setDays(e.target.value)}
              />
            </div>
            <Button variant="outline" onClick={() => load(num(days) || 7)} disabled={loading}>
              {loading ? "Reading the stores…" : "Recalculate"}
            </Button>
            {loading && <Loader2 className="h-4 w-4 animate-spin text-[var(--sd-quiet)]" />}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {plan && (
            <FigureRow>
              <Figure
                label="Total to mix"
                value={fmt(plan.total_to_mix_kg)}
                unit="kg"
                hint={`covers ${plan.days} day${plan.days === 1 ? "" : "s"}`}
              />
              <Figure
                label="Whole batches"
                value={String(plan.total_batches)}
                hint={`${fmt(plan.batch_kg)} kg each`}
              />
              <Figure
                label="Concentrates in play"
                value={String(plan.concentrates.length)}
                hint="drawn on by a herd ration"
              />
              <Figure
                label="Cannot be mixed yet"
                value={String(shortRows.length)}
                hint={shortRows.length ? "raw material short" : "nothing blocked"}
              />
            </FigureRow>
          )}
          <PlanTable plan={plan} error={error} />
        </CardContent>
      </Card>

      {shortRows.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>What is blocking a batch</CardTitle>
            <CardDescription>
              These batches are in the plan but the raw materials are not in the stores.
              Until they are, the figure above is a target, not a job.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {shortRows.map((c) => (
              <div
                key={c.item_code}
                className="flex flex-col gap-2 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] px-4 py-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-semibold text-[var(--sd-ink)]">
                    {c.item_name}
                  </span>
                  <Pill tone="short">
                    {c.batches} batch{c.batches === 1 ? "" : "es"} — {fmt(c.to_mix_kg)} kg
                  </Pill>
                </div>
                <ul className="flex flex-col gap-1 text-[13px] text-[var(--sd-muted)]">
                  {c.short.map((s, i) => (
                    <li key={`${s.item_code || s.item_name || i}`}>
                      Short: {s.item_name || s.item_code}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Notice tone="info">
        Mixing a batch is not wired into this page. Run it from the Livestock Operations
        block on the desk, which is live and unchanged.
      </Notice>
    </Page>
  );
}
