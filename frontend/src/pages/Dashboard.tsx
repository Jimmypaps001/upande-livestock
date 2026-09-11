import { useEffect, useMemo, useState } from "react";
import { MilkChart } from "@/components/dashboard/MilkChart";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { HEADER_PILL } from "@/components/header-controls";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeaderRow,
  CardHeading,
  CardTitle,
  CardTools,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { isError } from "@/lib/frappe";
import {
  ALL_HERDS,
  dailySeries,
  getProduction,
  perCow,
  type ProductionPayload,
} from "@/lib/production";
import { fmt } from "@/lib/utils";

const WINDOWS = [
  { days: 14, label: "Last 14 days" },
  { days: 30, label: "Last 30 days" },
  { days: 90, label: "Last 90 days" },
  { days: 0, label: "Everything recorded" },
] as const;

/**
 * Milk production over time.
 *
 * The chart is the page: one line, litres — kilograms, on this farm — against
 * the day they were recorded. Everything else on the page exists to say what
 * that line is made of.
 *
 * The figures under it are the endpoint's own 30-day rollup, not a re-sum of
 * the visible window, so they do not change when the window does. They are
 * labelled as 30-day for exactly that reason.
 */
export function Dashboard() {
  const [data, setData] = useState<ProductionPayload | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [herd, setHerd] = useState<string>(ALL_HERDS);
  const [days, setDays] = useState<number>(30);

  async function load() {
    setLoading(true);
    const r = await getProduction();
    setLoading(false);
    if (isError(r)) {
      setData(null);
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setData(r);
  }

  useEffect(() => {
    load();
  }, []);

  const points = useMemo(
    () => dailySeries(data?.rows || [], { herd, days }),
    [data, herd, days],
  );

  const windowTotal = points.reduce((s, p) => s + p.net_kg, 0);
  const best = points.reduce<null | (typeof points)[number]>(
    (b, p) => (!b || p.net_kg > b.net_kg ? p : b),
    null,
  );
  const latest = points.length ? points[points.length - 1] : null;
  const latestPerCow = latest ? perCow(latest) : null;
  const summary = data?.summary || {};
  const herds = data?.filters?.herds || [];

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Dashboard" title="Milk production">
        Every Milk Recording, folded into one point per day. The farm milks twice, so a
        day is the sum of its sessions. Quantities are kilograms — the unit every Milk
        Recording is written in.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Net milk against date</CardTitle>
            <CardDescription>
              Net is what was sellable — total yield less anything discarded. Hover a
              point for the day's figure.
            </CardDescription>
          </CardHeading>
          <CardTools>
            <Select value={herd} onValueChange={setHerd}>
              <SelectTrigger id="dash-herd" aria-label="Herd" className={HEADER_PILL}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_HERDS}>Every herd</SelectItem>
                {herds.map((h) => (
                  <SelectItem key={h} value={h}>
                    {h}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
              <SelectTrigger id="dash-window" aria-label="Window" className={HEADER_PILL}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WINDOWS.map((w) => (
                  <SelectItem key={w.days} value={String(w.days)}>
                    {w.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <RefreshButton onClick={load} loading={loading} label="the recordings" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-5">
          <MilkChart points={points} />
          <FigureRow>
            <Figure
              label="In this window"
              value={fmt(windowTotal)}
              unit="kg"
              hint={`${points.length} day${points.length === 1 ? "" : "s"} recorded`}
            />
            <Figure
              label="Last recorded day"
              value={latest ? fmt(latest.net_kg) : "—"}
              unit="kg"
              hint={latest ? latest.date : undefined}
            />
            <Figure
              label="Best day"
              value={best ? fmt(best.net_kg) : "—"}
              unit="kg"
              hint={best ? best.date : undefined}
            />
            <Figure
              label="Per cow, last day"
              value={latestPerCow == null ? "—" : fmt(latestPerCow)}
              unit="kg"
              hint={latest && latest.cows ? `${latest.cows} cows milked` : undefined}
            />
          </FigureRow>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>The last 30 days</CardTitle>
          <CardDescription>
            The endpoint's own rollup across every herd. It does not follow the filters
            above.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <FigureRow>
            <Figure label="Net milk" value={fmt(summary.net_kg)} unit="kg" />
            <Figure label="Discarded" value={fmt(summary.discarded_kg)} unit="kg" />
            <Figure label="Revenue" value={fmt(summary.revenue)} unit="KES" />
            <Figure
              label="Recordings"
              value={String(summary.records ?? 0)}
              hint="milking sessions filed"
            />
          </FigureRow>
          <FigureRow>
            <Figure label="Average protein" value={fmt(summary.avg_protein)} unit="%" />
            <Figure
              label="Average bulk SCC"
              value={fmt(summary.avg_scc)}
              unit="×1000 cells/ml"
            />
          </FigureRow>
        </CardContent>
      </Card>
    </Page>
  );
}
