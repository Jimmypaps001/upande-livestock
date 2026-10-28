import { useCallback, useEffect, useRef, useState } from "react";
import { Notice } from "@/components/feeding/Notice";
import { AccuracyTab } from "@/components/forecast/AccuracyTab";
import { CoverTab } from "@/components/forecast/CoverTab";
import { OutputTab } from "@/components/forecast/OutputTab";
import { TrendTab } from "@/components/forecast/TrendTab";
import { HEADER_PILL } from "@/components/header-controls";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Card, CardContent, CardHeaderRow, CardHeading, CardTitle, CardTools } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ALL_HERDS,
  DEFAULT_WEEKS,
  WEEK_OPTIONS,
  getCommitmentCover,
  getForecastAccuracy,
  getOutputForecast,
  getProductivityTrend,
  type AccuracyRow,
  type CoverRow,
  type OutputForecast,
  type TrendView,
} from "@/lib/forecast";
import { isError } from "@/lib/frappe";
import { listPerformanceHerds, type PerformanceHerd } from "@/lib/performance";
import { cn } from "@/lib/utils";

type Tab = "output" | "cover" | "trend" | "accuracy";
const TABS: Array<[Tab, string]> = [
  ["output", "Output"],
  ["cover", "Cover"],
  ["trend", "Trend"],
  ["accuracy", "Accuracy"],
];

/** Production · Forecast: when bulls reach exit weight, against what buyers expect. */
export function Forecast() {
  const [tab, setTab] = useState<Tab>("output");
  const [herds, setHerds] = useState<PerformanceHerd[]>([]);
  const [herd, setHerd] = useState(ALL_HERDS);
  const [weeks, setWeeks] = useState<number>(DEFAULT_WEEKS);
  const [output, setOutput] = useState<OutputForecast | null>(null);
  const [cover, setCover] = useState<CoverRow[] | null>(null);
  const [trend, setTrend] = useState<TrendView | null>(null);
  const [accuracy, setAccuracy] = useState<AccuracyRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void listPerformanceHerds().then((r) => {
      if (live && Array.isArray(r)) setHerds(r);
    });
    return () => {
      live = false;
    };
  }, []);

  // Only the newest request may write.
  const latest = useRef(0);
  const load = useCallback(async () => {
    const mine = ++latest.current;
    const h = herd === ALL_HERDS ? undefined : herd;
    setLoading(true);
    let err: string | null = null;
    if (tab === "output") {
      const r = await getOutputForecast(weeks, h);
      if (mine !== latest.current) return;
      if (isError(r)) err = r.error;
      else setOutput(r as OutputForecast);
    } else if (tab === "cover") {
      const r = await getCommitmentCover(weeks);
      if (mine !== latest.current) return;
      if (isError(r)) err = r.error;
      else setCover((r as { weeks: CoverRow[] }).weeks);
    } else if (tab === "trend") {
      const r = await getProductivityTrend(26, h);
      if (mine !== latest.current) return;
      if (isError(r)) err = r.error;
      else setTrend(r as TrendView);
    } else {
      const r = await getForecastAccuracy(weeks, h);
      if (mine !== latest.current) return;
      if (isError(r)) err = r.error;
      else setAccuracy((r as { weeks: AccuracyRow[] }).weeks);
    }
    setFailure(err);
    setLoading(false);
  }, [tab, herd, weeks]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Beef" title="Production Forecast">
        When each bull reaches exit weight, what that means week by week, and how it lines up with
        what buyers have asked for.
      </PageHeading>
      {failure && <Notice tone="error">{failure}</Notice>}
      <Card>
        <CardHeaderRow className="flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardHeading>
            <CardTitle>Forecast</CardTitle>
          </CardHeading>
          <CardTools>
            <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
              <TabsList>
                {TABS.map(([v, label]) => (
                  <TabsTrigger key={v} value={v}>
                    {label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            {tab !== "cover" && (
              <Select value={herd} onValueChange={setHerd}>
                <SelectTrigger aria-label="Herd" className={cn(HEADER_PILL, "max-w-[14rem]")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_HERDS}>Every herd</SelectItem>
                  {herds.map((h) => (
                    <SelectItem key={h.herd} value={h.herd}>
                      {h.herd}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {tab !== "trend" && (
              <Select value={String(weeks)} onValueChange={(v) => setWeeks(Number(v))}>
                <SelectTrigger aria-label="Weeks" className={HEADER_PILL}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {WEEK_OPTIONS.map((w) => (
                    <SelectItem key={w} value={String(w)}>
                      {w} weeks
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <RefreshButton onClick={load} loading={loading} label="the forecast" />
          </CardTools>
        </CardHeaderRow>
        <CardContent>
          {tab === "output" && <OutputTab data={output} loading={loading} />}
          {tab === "cover" && <CoverTab rows={cover} loading={loading} onSaved={load} />}
          {tab === "trend" && <TrendTab data={trend} loading={loading} />}
          {tab === "accuracy" && <AccuracyTab rows={accuracy} loading={loading} />}
        </CardContent>
      </Card>
    </Page>
  );
}
