import { useState } from "react";
import { Pill } from "@/components/feeding/Notice";
import { Figure, FigureRow } from "@/components/Figure";
import { RowsSkeleton } from "@/components/Loading";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { HEADER_PILL } from "@/components/header-controls";
import {
  SCENARIOS,
  SCENARIO_LABEL,
  daysTone,
  fmtDaysLeft,
  fmtFeed,
  weeksOf,
  type FeedProjection,
  type Scenario,
} from "@/lib/feed-projection";
import { fmtKg } from "@/lib/forecast";
import { cn } from "@/lib/utils";

const TH = "px-3 py-2.5 font-medium";
const HEAD_ROW = "border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]";
const BOX = "overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]";

function DaysLeft({ days, weeks }: { days: number | null; weeks: number }) {
  const tone = daysTone(days);
  const text = fmtDaysLeft(days, weeks);
  if (tone === "warn") {
    return (
      <span className="inline-flex items-center rounded-[var(--sd-radius-pill)] bg-[var(--sd-amber-bg)] px-2.5 py-1 text-[11px] font-medium text-[var(--sd-amber)]">
        {text}
      </span>
    );
  }
  return <Pill tone={tone}>{text}</Pill>;
}

/** Weekly feed as bars: the expected case, with the low and high cases as ticks. */
function FeedBars({ data }: { data: FeedProjection }) {
  const rows = data.total.weeks.expected.map((w, i) => ({
    start: w.week_start,
    exp: w.feed_kg,
    lo: data.total.weeks.low[i].feed_kg,
    hi: data.total.weeks.high[i].feed_kg,
  }));
  const max = Math.max(1, ...rows.map((r) => Math.max(r.exp, r.lo, r.hi)));
  return (
    <div
      className="flex h-32 items-end gap-1.5 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] px-3 pb-2 pt-3"
      role="img"
      aria-label="Feed needed per week"
      data-testid="feed-bars"
    >
      {rows.map((r) => (
        <div
          key={r.start}
          className="relative flex h-full min-w-0 flex-1 flex-col justify-end"
          title={`${r.start}: ${fmtFeed(r.exp)} (low ${fmtFeed(r.lo)}, high ${fmtFeed(r.hi)})`}
        >
          <div className="w-full rounded-t bg-[var(--sd-ink)]" style={{ height: `${(r.exp / max) * 100}%`, minHeight: 2 }} />
          <div className="absolute inset-x-0 h-px bg-[var(--sd-amber)]" style={{ bottom: `${(r.lo / max) * 100}%` }} />
          <div className="absolute inset-x-0 h-px bg-[var(--sd-amber)]" style={{ bottom: `${(r.hi / max) * 100}%` }} />
        </div>
      ))}
    </div>
  );
}

/** Production · Forecast · Feed: today's herd, the feed it needs, and a projection forward. */
export function FeedTab({ data, loading }: { data: FeedProjection | null; loading: boolean }) {
  const [scenario, setScenario] = useState<Scenario>("expected");
  if (!data) {
    return loading ? (
      <RowsSkeleton rows={8} />
    ) : (
      <p className="px-1 py-6 text-center text-[13px] text-[var(--sd-muted)]">The feed projection could not be loaded.</p>
    );
  }
  const t = data.total;
  const weeks = t.weeks[scenario];
  const last = weeks[weeks.length - 1];
  const needed = last ? last.cumulative_kg : 0;
  return (
    <div className="flex flex-col gap-3">
      <FigureRow>
        <Figure label="Head today" value={fmtKg(t.head)} unit="head" hint={t.calves ? `${t.calves} calves not fed` : undefined} />
        <Figure label="Live weight" value={fmtFeed(t.live_kg)} />
        <Figure label="Feed a day" value={fmtFeed(t.day_kg)} hint={`${data.settings.dm_intake_pct}% of live weight`} />
        <Figure label="Feed in store" value={fmtFeed(t.stock_kg)} hint={`${fmtDaysLeft(t.days_left.today_rate, data.weeks)} at today's rate`} />
        <Figure
          label={`Needed in ${data.weeks} weeks`}
          value={fmtFeed(needed)}
          hint={SCENARIO_LABEL[scenario]}
        />
      </FigureRow>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-1" data-testid="feed-days-left">
        <span className="text-[12.5px] text-[var(--sd-muted)]">Days of feed left</span>
        {SCENARIOS.map((s) => (
          <span key={s} className="inline-flex items-center gap-2 text-[12.5px] text-[var(--sd-muted)]">
            {SCENARIO_LABEL[s]}
            <DaysLeft days={t.days_left[s]} weeks={data.weeks} />
          </span>
        ))}
        <span className="ml-auto">
          <Select value={scenario} onValueChange={(v) => setScenario(v as Scenario)}>
            <SelectTrigger aria-label="Gain case" className={cn(HEADER_PILL)}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCENARIOS.map((s) => (
                <SelectItem key={s} value={s}>
                  {SCENARIO_LABEL[s]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </span>
      </div>

      <FeedBars data={data} />
      <p className="px-1 text-[11.5px] text-[var(--sd-quiet)]">
        Bars are the expected feed per week; the amber ticks are the low and high gain cases.
      </p>

      <h3 className="px-1 pt-2 text-[13px] font-medium text-[var(--sd-ink)]">By herd, today</h3>
      <div className={BOX}>
        <table className="w-full min-w-[56rem] text-[13px]" data-testid="feed-herds">
          <thead>
            <tr className={HEAD_ROW}>
              <th className={TH}>Herd</th>
              <th className={cn(TH, "text-right")}>Head</th>
              <th className={cn(TH, "text-right")}>Live weight</th>
              <th className={cn(TH, "text-right")}>Average</th>
              <th className={cn(TH, "text-right")}>Feed a day</th>
              <th className={cn(TH, "text-right")}>Needed ({data.weeks} wk)</th>
              <th className={TH}>Stands on</th>
              <th className={cn(TH, "text-right")}>Feed days left</th>
            </tr>
          </thead>
          <tbody>
            {data.herds.map((h) => {
              const hw = weeksOf(h, scenario);
              const need = hw.length ? hw[hw.length - 1].cumulative_kg : 0;
              return (
                <tr key={h.herd} className="border-b border-[var(--sd-line-soft)] last:border-0">
                  <td className="px-3 py-2.5 font-medium text-[var(--sd-ink)]">{h.herd}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {h.head}
                    {h.calves ? <span className="text-[var(--sd-quiet)]"> ({h.calves} calves)</span> : null}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtFeed(h.live_kg)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{h.avg_kg === null ? "—" : `${fmtKg(h.avg_kg)} kg`}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtFeed(h.day_kg)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtFeed(need)}</td>
                  <td className="px-3 py-2.5 text-[var(--sd-muted)]">{h.paddock ? h.paddock.replace(/ - [A-Z]+$/, "") : "—"}</td>
                  <td className="px-3 py-2.5 text-right">
                    {h.days_left ? <DaysLeft days={h.days_left[scenario]} weeks={data.weeks} /> : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <h3 className="px-1 pt-2 text-[13px] font-medium text-[var(--sd-ink)]">Week by week, {SCENARIO_LABEL[scenario].toLowerCase()}</h3>
      <div className={BOX}>
        <table className="w-full min-w-[40rem] text-[13px]" data-testid="feed-weeks">
          <thead>
            <tr className={HEAD_ROW}>
              <th className={TH}>Week of</th>
              <th className={cn(TH, "text-right")}>Head</th>
              <th className={cn(TH, "text-right")}>Average weight</th>
              <th className={cn(TH, "text-right")}>Leave</th>
              <th className={cn(TH, "text-right")}>Feed</th>
              <th className={cn(TH, "text-right")}>Cumulative</th>
              <th className={cn(TH, "text-right")}>Store left</th>
            </tr>
          </thead>
          <tbody>
            {weeks.map((w) => {
              const left = t.stock_kg - w.cumulative_kg;
              return (
                <tr key={w.week_start} className="border-b border-[var(--sd-line-soft)] last:border-0">
                  <td className="px-3 py-2.5 tabular-nums">{w.week_start}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{w.head}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{w.avg_kg === null ? "—" : `${fmtKg(w.avg_kg)} kg`}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{w.exits || "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtFeed(w.feed_kg)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtFeed(w.cumulative_kg)}</td>
                  <td className={cn("px-3 py-2.5 text-right tabular-nums", left < 0 && "text-[var(--sd-sev-critical)]")}>
                    {left < 0 ? `short ${fmtFeed(-left)}` : fmtFeed(left)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {data.bands && (
        <>
          <h3 className="px-1 pt-2 text-[13px] font-medium text-[var(--sd-ink)]">Feedlot weight bands</h3>
          <div className={BOX}>
            <table className="w-full min-w-[36rem] text-[13px]" data-testid="feed-bands">
              <thead>
                <tr className={HEAD_ROW}>
                  <th className={TH}>Week of</th>
                  {data.bands.names.map((n) => (
                    <th key={n} className={cn(TH, "text-right")}>
                      {n}
                    </th>
                  ))}
                  <th className={cn(TH, "text-right")}>Reach exit weight</th>
                  <th className={TH}>Moves up</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-[var(--sd-line-soft)]">
                  <td className="px-3 py-2.5 text-[var(--sd-muted)]">Today</td>
                  {data.bands.names.map((n) => (
                    <td key={n} className="px-3 py-2.5 text-right tabular-nums">
                      {data.bands!.today[n] ?? 0}
                    </td>
                  ))}
                  <td className="px-3 py-2.5 text-right">—</td>
                  <td className="px-3 py-2.5">—</td>
                </tr>
                {data.bands.weeks.map((w) => (
                  <tr key={w.week_start} className="border-b border-[var(--sd-line-soft)] last:border-0">
                    <td className="px-3 py-2.5 tabular-nums">{w.week_start}</td>
                    {data.bands!.names.map((n) => (
                      <td key={n} className="px-3 py-2.5 text-right tabular-nums">
                        {w.counts[n] ?? 0}
                      </td>
                    ))}
                    <td className="px-3 py-2.5 text-right tabular-nums">{w.exits || "—"}</td>
                    <td className="px-3 py-2.5 text-[var(--sd-muted)]">
                      {w.moves.length ? w.moves.map((m) => `${m.head} ${m.from} to ${m.to}`).join(", ") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h3 className="px-1 pt-2 text-[13px] font-medium text-[var(--sd-ink)]">Feed in store</h3>
      <div className={BOX}>
        <table className="w-full min-w-[30rem] text-[13px]" data-testid="feed-stock">
          <thead>
            <tr className={HEAD_ROW}>
              <th className={TH}>Item</th>
              <th className={TH}>Store</th>
              <th className={cn(TH, "text-right")}>On hand</th>
            </tr>
          </thead>
          <tbody>
            {data.stock.items.map((i) => (
              <tr key={`${i.item_code}-${i.warehouse}`} className="border-b border-[var(--sd-line-soft)] last:border-0">
                <td className="px-3 py-2.5 font-medium text-[var(--sd-ink)]">{i.item_name}</td>
                <td className="px-3 py-2.5 text-[var(--sd-muted)]">{i.warehouse.replace(/ - [A-Z]+$/, "")}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmtFeed(i.kg)}</td>
              </tr>
            ))}
            {data.stock.items.length === 0 && (
              <tr>
                <td colSpan={3} className="px-3 py-4 text-center text-[var(--sd-muted)]">
                  No feed in the feed stores.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <ul className="flex flex-col gap-1 px-1 text-[11.5px] text-[var(--sd-quiet)]" data-testid="feed-notes">
        {data.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </div>
  );
}
