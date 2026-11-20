import { useEffect, useState } from "react";
import { TrendingDown } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle } from "@/components/ui/card";
import { Figure, FigureRow } from "@/components/Figure";
import { Skeleton } from "@/components/ui/skeleton";
import {
  burdenMarker,
  getBullEconomics,
  money,
  type BullEconomics,
  type BullGrowth,
} from "@/lib/bulls";
import { isError } from "@/lib/frappe";

/** "Burden since <date>" in the loss colour; nothing when feed has not passed value. */
export function BurdenMarker({ economics }: { economics: BullEconomics }) {
  const text = burdenMarker(economics);
  if (!text) return null;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] px-3 py-1 text-[12px] font-semibold text-[var(--sd-sev-critical)]">
      <TrendingDown className="h-3.5 w-3.5" />
      {text}
    </span>
  );
}

function Spark({ growth }: { growth: BullGrowth }) {
  const s = growth.series;
  if (s.length < 2) return null;
  const kgs = s.map((p) => p.kg);
  const lo = Math.min(...kgs);
  const hi = Math.max(...kgs);
  const pts = s
    .map((p, i) => `${(i / (s.length - 1)) * 100},${hi === lo ? 20 : 38 - ((p.kg - lo) / (hi - lo)) * 36}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-10 w-full" role="img" aria-label="Weight over time">
      <polyline points={pts} fill="none" stroke="var(--sd-data-green)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/**
 * A bull's page in place of the calving loop: how he is growing, what he has
 * eaten, what he is worth, and — for a farm that sells bulls at birth — every
 * day he is kept counted as cost.
 */
export function BullPanel({ animal }: { animal: string }) {
  const [e, setE] = useState<BullEconomics | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setE(null);
    setFailure(null);
    void getBullEconomics(animal).then((r) => {
      if (!live) return;
      if (isError(r)) setFailure(r.error);
      else setE(r);
    });
    return () => {
      live = false;
    };
  }, [animal]);

  const loss = e?.net != null && e.net < 0;
  const g = e?.growth ?? null;

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Weight and growth</CardTitle>
            <CardDescription>From the weight records.</CardDescription>
          </CardHeading>
          {e && <BurdenMarker economics={e} />}
        </CardHeaderRow>
        <CardContent className="pt-0">
          {failure ? (
            <p className="text-[13px] text-[var(--sd-sev-critical)]">{failure}</p>
          ) : g ? (
            <div className="flex flex-col gap-3">
              <FigureRow>
                <Figure label="Weight" value={g.kg == null ? "—" : String(g.kg)} unit={g.kg == null ? undefined : "kg"} hint={g.on ? `weighed ${g.on}` : "not weighed"} />
                <Figure label="Daily gain" value={g.adg == null ? "—" : g.adg.toFixed(2)} unit={g.adg == null ? undefined : "kg/d"} />
                <Figure label="Birth weight" value={g.birth_kg == null ? "—" : String(g.birth_kg)} unit={g.birth_kg == null ? undefined : "kg"} />
                <Figure label="Days kept" value={e?.days_kept == null ? "—" : String(e.days_kept)} />
              </FigureRow>
              <Spark growth={g} />
            </div>
          ) : (
            <Skeleton className="h-24 w-full" />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Feed against value</CardTitle>
            <CardDescription>{e?.feed.method ?? "Herd feed cost per head, day by day."}</CardDescription>
          </CardHeading>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-3 pt-0">
          <FigureRow>
            <Figure
              loading={!e}
              label="Feed cost to date"
              value={e ? money(e.feed.cost, e.currency) : "—"}
              hint={e ? `${e.feed.days_fed} days fed` : undefined}
            />
            <Figure
              loading={!e}
              label="Value now"
              value={e ? money(e.value.amount, e.currency) : "—"}
              hint={e?.value.source === "asset" ? "from his asset" : e?.value.source === "price_per_kg" ? "price per kg × weight" : "no asset or price"}
            />
            <Figure
              loading={!e}
              label={loss ? "Net (loss)" : "Net"}
              value={e ? money(e.net, e.currency) : "—"}
            />
          </FigureRow>
          {e?.kept_as_cost && (
            <p className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3 py-2 text-[12.5px] text-[var(--sd-sev-critical)]">
              Purpose: {e.purpose}. Bulls are sold as soon as they are born, so every day he is kept is cost
              {e.days_kept != null ? ` — ${e.days_kept} days so far` : ""}
              {e.feed.per_day != null ? `, about ${money(e.feed.per_day, e.currency)} a day` : ""}.
            </p>
          )}
          {e && !e.kept_as_cost && <p className="text-[12.5px] text-[var(--sd-muted)]">Purpose: {e.purpose}.</p>}
        </CardContent>
      </Card>
    </div>
  );
}
