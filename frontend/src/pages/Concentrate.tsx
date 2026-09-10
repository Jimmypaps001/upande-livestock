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
import {
  concentratePlan,
  manufactureConcentrate,
  type ConcentrateWeeklyPlan,
  type ConcentrateWeeklyRow,
} from "@/lib/feeding";
import { fmt, num } from "@/lib/utils";

/**
 * Concentrate: what the farm holds and what it must mix — and the mixer runs
 * from here.
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
 * `manufacture_concentrate` is the same Work Order → transfer → manufacture
 * route the desk's Livestock Operations block already runs. `can_mix` is
 * checked here before a request is ever sent — the plan already knows a row
 * is short, so refusing locally is a better answer than a round trip to a
 * stock error. Only one row runs at a time: the whole plan is refreshed after
 * a mix because a batch changes the raw-material picture for every other row
 * that draws on the same ingredients, not just the one just run.
 *
 * `manufacture_concentrate` commits partway through (Work Order, then each
 * Stock Entry) rather than standing or falling as one transaction — a known,
 * deliberately deferred gap. A failure partway can leave a Work Order behind
 * with no Stock Entry against it, so a refusal here is not proof nothing
 * happened; the plan reload after every attempt is what surfaces the truth.
 */
export function Concentrate() {
  const [days, setDays] = useState("7");
  const [plan, setPlan] = useState<ConcentrateWeeklyPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>({});
  const [mixingItem, setMixingItem] = useState<string | null>(null);
  const [mixError, setMixError] = useState<string | null>(null);
  const [mixSuccess, setMixSuccess] = useState<string | null>(null);

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
    // Fresh figures from the server replace whatever the operator had typed —
    // an edited quantity from before a mix belongs to a plan that no longer
    // exists.
    setQtyByItem({});
  }, []);

  useEffect(() => {
    load(7);
  }, [load]);

  function changeQty(itemCode: string, value: string) {
    setQtyByItem((prev) => ({ ...prev, [itemCode]: value }));
  }

  async function mix(row: ConcentrateWeeklyRow) {
    setMixError(null);
    setMixSuccess(null);
    // The plan already knows this row is short; do not send it and let the
    // server refuse.
    if (!row.can_mix) {
      const short = row.short.map((s) => s.item_name || s.item_code).filter(Boolean);
      setMixError(
        `${row.item_name} cannot be mixed yet${short.length ? ` — short: ${short.join(", ")}.` : "."}`,
      );
      return;
    }
    const qty = num(qtyByItem[row.item_code] ?? String(row.to_mix_kg));
    if (qty <= 0) {
      setMixError("Enter a quantity greater than zero.");
      return;
    }
    setMixingItem(row.item_code);
    const r = await manufactureConcentrate({
      item_code: row.item_code,
      qty,
      bom_no: row.bom_no,
    });
    setMixingItem(null);
    if (isError(r)) {
      setMixError(r.error);
      return;
    }
    setMixSuccess(
      `Mixed ${fmt(r.produced_qty)} ${r.uom || "kg"} of ${row.item_name} — Work Order ${
        r.work_order
      }.`,
    );
    load(plan?.days || num(days) || 7);
  }

  const shortRows = (plan?.concentrates || []).filter(
    (c) => c.to_mix_kg > 0 && !c.can_mix,
  );

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Feeding" title="Concentrate">
        How much of each concentrate the herds will eat over the days you set, what the
        stores already hold, and how many whole batches close the gap. Run a batch
        straight from a row below once the raw materials cover it.
      </PageHeading>

      {mixError && <Notice tone="error">{mixError}</Notice>}
      {mixSuccess && <Notice tone="ok">{mixSuccess}</Notice>}

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
          <PlanTable
            plan={plan}
            error={error}
            qtyByItem={qtyByItem}
            onQtyChange={changeQty}
            onMix={mix}
            mixingItem={mixingItem}
          />
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
    </Page>
  );
}
