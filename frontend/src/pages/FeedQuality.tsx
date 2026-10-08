import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { HERD_COLOURS, QualityTrendChart } from "@/components/quality/QualityTrendChart";
import { RefreshButton } from "@/components/RefreshButton";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { isError } from "@/lib/frappe";
import {
  fetchFeedQuality,
  formatMetric,
  METRICS,
  type FeedQuality as FeedQualityData,
  type HerdFeedQuality,
  type Metric,
} from "@/lib/feed-quality";
import { cn, fmt } from "@/lib/utils";

/**
 * Milk quality beside what each milking herd is fed.
 *
 * The question a ration trial asks: is the milk from the herd on the new recipe
 * better than everyone else's? Each herd's card puts its ration — kilograms a
 * head a day, how much of it is concentrate — next to its butterfat, protein,
 * cell count and yield, each set against the other milking herds together.
 * The chart below follows one figure week by week.
 *
 * Quality is what the lab put on each milking (the Quality page); feed is the
 * herd's standing recipe, and what was actually issued to it when the window
 * holds any feed runs.
 */

function Pill({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        "h-7 rounded-full border px-3 text-[12px] font-medium transition-colors",
        on
          ? "border-[var(--sd-ink)] bg-[var(--sd-ink)] text-white"
          : "border-[var(--sd-line)] text-[var(--sd-muted)] hover:bg-[var(--sd-bg-soft)]",
      )}
    >
      {children}
    </button>
  );
}

/** "+18.7% vs other herds", with the arrow saying which way and the words
 *  saying whether that is good — never colour alone. */
function Delta({ metric, pct }: { metric: Metric; pct: number | null }) {
  if (pct == null) return <span className="text-[11.5px] text-[var(--sd-quiet)]">no other herd to compare</span>;
  const up = pct >= 0;
  const better = METRICS[metric].better === "higher" ? up : !up;
  const Icon = up ? ArrowUp : ArrowDown;
  return (
    <span className="inline-flex items-center gap-1 text-[11.5px] text-[var(--sd-muted)]">
      <Icon className="h-3 w-3" aria-hidden />
      {up ? "+" : "−"}
      {Math.abs(pct).toFixed(1)}% vs other herds
      <span className={cn("ml-1 rounded px-1 text-[10.5px] font-medium", better ? "bg-[var(--sd-alert-ok)] text-[#1f7a3d]" : "bg-[var(--sd-amber-bg)] text-[var(--sd-amber)]")}>
        {better ? "better" : "worse"}
      </span>
    </span>
  );
}

function Stat({ label, value, children }: { label: string; value: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-[var(--sd-quiet)]">{label}</span>
      <span className="text-[20px] font-semibold tabular-nums tracking-[-0.01em] text-[var(--sd-ink)]">{value}</span>
      {children}
    </div>
  );
}

function HerdCard({ h, colour }: { h: HerdFeedQuality; colour: string }) {
  const r = h.ration;
  return (
    <Card aria-label={h.herd}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-[15px]">
          <span aria-hidden className="size-2.5 rounded-full" style={{ background: colour }} />
          {h.herd}
        </CardTitle>
        <CardDescription>
          {h.cows} cows · {h.quality.milkings} milkings, {h.quality.readings} with lab figures
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <section aria-label="Feed" className="rounded-md border border-[var(--sd-line)] bg-[var(--sd-bg-soft)] p-3">
          <div className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-[var(--sd-quiet)]">Ration</div>
          {r ? (
            <>
              <div className="mt-0.5 text-[13.5px] font-medium text-[var(--sd-ink)]">{r.name}</div>
              <div className="text-[12.5px] text-[var(--sd-muted)]">
                {fmt(r.per_head)} {r.uom} a head a day
                {r.concentrate_share != null &&
                  ` · ${Math.round(r.concentrate_share * 100)}% concentrate (${fmt(r.concentrate_kg)} kg)`}
              </div>
              <ul className="mt-2 flex flex-col gap-0.5 text-[12px] text-[var(--sd-text)]">
                {r.lines.slice(0, 5).map((ln) => (
                  <li key={ln.item_code} className="flex justify-between gap-3">
                    <span className="truncate">
                      {ln.item_name}
                      {ln.concentrate && <span className="ml-1 text-[var(--sd-quiet)]">· concentrate</span>}
                    </span>
                    <span className="shrink-0 tabular-nums text-[var(--sd-muted)]">
                      {fmt(ln.qty)} {ln.uom}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <div className="mt-0.5 text-[12.5px] text-[var(--sd-muted)]">This herd has no ration recipe.</div>
          )}
          <div className="mt-2 text-[11.5px] text-[var(--sd-quiet)]">
            {h.fed.runs
              ? `Issued in this window: ${h.fed.runs} feed run${h.fed.runs === 1 ? "" : "s"}, ${fmt(h.fed.kg)} kg`
              : "No feed runs recorded in this window"}
          </div>
        </section>
        <div className="grid grid-cols-2 gap-4">
          <Stat label="Butterfat" value={formatMetric("fat", h.quality.fat)}>
            <Delta metric="fat" pct={h.vs_rest.fat} />
          </Stat>
          <Stat label="Protein" value={formatMetric("protein", h.quality.protein)}>
            <Delta metric="protein" pct={h.vs_rest.protein} />
          </Stat>
          <Stat label="Somatic cells" value={formatMetric("scc", h.quality.scc)}>
            <Delta metric="scc" pct={h.vs_rest.scc} />
          </Stat>
          <Stat
            label="Milk a cow a day"
            value={h.quality.milk_per_cow_day != null ? `${fmt(h.quality.milk_per_cow_day)} kg` : "—"}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function WeekTable({ data, metric }: { data: FeedQualityData; metric: Metric }) {
  const head = "px-3 py-2 text-left text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--sd-quiet)]";
  const cell = "px-3 py-2 text-[13px] tabular-nums text-[var(--sd-text)]";
  return (
    <div className="overflow-x-auto rounded-md border border-[var(--sd-line)] bg-[var(--sd-card)]">
      <table className="w-full min-w-[32rem] border-collapse" aria-label={`${METRICS[metric].label} by week`}>
        <thead>
          <tr className="border-b border-[var(--sd-line)]">
            <th className={head}>Week starting</th>
            {data.herds.map((h) => (
              <th key={h.herd} className={head}>
                {h.herd}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.weeks.map((w) => (
            <tr key={w.week} className="border-t border-[var(--sd-line)]">
              <td className={cell}>{w.week}</td>
              {data.herds.map((h) => (
                <td key={h.herd} className={cell}>
                  {formatMetric(metric, w.herds[h.herd]?.[metric])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FeedQuality() {
  const [days, setDays] = useState(90);
  const [metric, setMetric] = useState<Metric>("fat");
  const [asTable, setAsTable] = useState(false);
  const [data, setData] = useState<FeedQualityData | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (d: number) => {
    setLoading(true);
    const r = await fetchFeedQuality(d);
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setData(r);
  }, []);

  useEffect(() => {
    void load(days);
  }, [days, load]);

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Milking" title="Quality & Feed">
        <p className="max-w-2xl text-[14px] leading-relaxed text-[var(--sd-muted)]">
          Each milking herd&rsquo;s milk quality beside what it is fed — set against the other herds, so a
          ration trial shows whether the new recipe is paying off.
        </p>
      </PageHeading>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Window">
          {(data?.windows ?? [30, 90, 150]).map((w) => (
            <Pill key={w} on={days === w} onClick={() => setDays(w)}>
              Last {w} days
            </Pill>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <span className="text-[12px] text-[var(--sd-quiet)]">
              {data.from_date} to {data.to_date}
            </span>
          )}
          <RefreshButton onClick={() => void load(days)} loading={loading} label="the quality figures" />
        </div>
      </div>

      {failure && <Notice tone="error">{failure}</Notice>}

      {data && (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            {data.herds.map((h, k) => (
              <HerdCard key={h.herd} h={h} colour={HERD_COLOURS[k % HERD_COLOURS.length]} />
            ))}
          </div>

          <Card>
            <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>{METRICS[metric].label} by week</CardTitle>
                <CardDescription>
                  The average of each week&rsquo;s milkings, per herd
                  {METRICS[metric].better === "lower" ? " — lower is better" : ""}.
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {(Object.keys(METRICS) as Metric[]).map((k) => (
                  <Pill key={k} on={metric === k} onClick={() => setMetric(k)}>
                    {METRICS[k].label}
                  </Pill>
                ))}
                <Pill on={asTable} onClick={() => setAsTable((v) => !v)}>
                  Table
                </Pill>
              </div>
            </CardHeader>
            <CardContent>
              {data.weeks.length === 0 ? (
                <p className="text-[13px] text-[var(--sd-muted)]">No milkings with lab figures in this window.</p>
              ) : asTable ? (
                <WeekTable data={data} metric={metric} />
              ) : (
                <QualityTrendChart data={data} metric={metric} />
              )}
            </CardContent>
          </Card>
        </>
      )}
    </Page>
  );
}
