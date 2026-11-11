import { useCallback, useEffect, useState } from "react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { RefreshButton } from "@/components/RefreshButton";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeaderRow,
  CardHeading,
  CardTitle,
  CardTools,
} from "@/components/ui/card";
import {
  fmtMoney,
  fmtPerAnimal,
  getCostPerAnimal,
  latestCostedDay,
  type CostReport,
} from "@/lib/costing";
import { isError } from "@/lib/frappe";
import { routeHash } from "@/lib/router";
import { todayISO } from "@/lib/utils";

/**
 * The Dashboard's Cost per animal panel: this month so far, and the latest
 * day that carried both animals and cost (today is usually not costed yet at
 * breakfast). The whole table is on the Costs page.
 *
 * A user without read on the labour book (the nutritionist) is refused by the
 * server; the panel then says nothing at all rather than showing a refusal on
 * the farm's front page.
 */
export function CostPanel() {
  const [data, setData] = useState<CostReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [refused, setRefused] = useState(false);

  const load = useCallback(async () => {
    const today = todayISO();
    setLoading(true);
    const r = await getCostPerAnimal(`${today.slice(0, 7)}-01`, today);
    setLoading(false);
    if (isError(r)) {
      if (/not permitted/i.test(r.error)) setRefused(true);
      else setFailure(r.error);
      return;
    }
    setFailure(null);
    setData(r as CostReport);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (refused) return null;
  const waiting = loading && !data;
  const day = data ? latestCostedDay(data.days || []) : null;

  return (
    <Card data-testid="cost-panel">
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Cost per animal</CardTitle>
          <CardDescription>
            Feed, medicine, labour and fuel over every animal on the farm.{" "}
            <a className="underline" href={routeHash("costs")}>
              The day-by-day table
            </a>
            .
          </CardDescription>
        </CardHeading>
        <CardTools>
          <RefreshButton onClick={load} loading={loading} label="the costs" />
        </CardTools>
      </CardHeaderRow>
      <CardContent className="flex flex-col gap-4">
        {failure && <Notice tone="error">{failure}</Notice>}
        <FigureRow>
          <Figure
            label="This month, per animal per day"
            value={fmtPerAnimal(data?.total?.cost_per_animal)}
            unit="KES"
            loading={waiting}
          />
          <Figure
            label={day ? `On ${day.date}` : "Latest day"}
            value={fmtPerAnimal(day?.cost_per_animal)}
            unit="KES"
            hint={day ? `${day.animals} animals` : "nothing costed yet"}
            loading={waiting}
          />
          <Figure
            label="This month so far"
            value={fmtMoney(data?.total?.total_cost)}
            unit="KES"
            loading={waiting}
          />
        </FigureRow>
      </CardContent>
    </Card>
  );
}
