import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { SessionChips } from "@/components/feeding/SessionChips";
import { DatePicker } from "@/components/DatePicker";
import { Page, PageHeading } from "@/components/PageShell";
import { ScrollTable, STICKY_HEAD } from "@/components/ScrollTable";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  APPETITE_LABEL,
  dailyFeedReport,
  pctText,
  type DailyFeedReport,
} from "@/lib/feed-actuals";
import { isError } from "@/lib/frappe";
import { cn, fmt, todayISO } from "@/lib/utils";

const ALL = "__all__";

const TONE = {
  below: "text-red-700",
  above: "text-amber-700",
  on_plan: "text-[var(--sd-muted)]",
} as const;

/**
 * Daily Feed Report: every animal fed on a day, planned kg a day beside what it
 * actually took, the variance, an appetite flag, and its latest weight and
 * average daily gain so appetite can be read against weight.
 */
export function FeedReport() {
  const [date, setDate] = useState(todayISO());
  const [herd, setHerd] = useState(ALL);
  const [report, setReport] = useState<DailyFeedReport | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [herdNames, setHerdNames] = useState<Array<{ herd: string; herd_name: string }>>([]);

  const load = useCallback(async () => {
    setReport(null);
    const r = await dailyFeedReport(date, herd === ALL ? undefined : herd);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setReport(r);
    // The filter lists the herds fed that day; only widened on an unfiltered read.
    if (herd === ALL) setHerdNames(r.herds.map((h) => ({ herd: h.herd, herd_name: h.herd_name })));
  }, [date, herd]);

  useEffect(() => {
    void load();
  }, [load]);

  const t = report?.totals;
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Feeding" title="Daily Feed Report">
        What each animal was fed on a day against its plan. Every animal shows how far
        above or below its plan it ate; there is no cut-off.
      </PageHeading>

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex w-56 flex-col gap-1.5">
          <span className="text-[13px] text-[var(--sd-muted)]">Day</span>
          <DatePicker value={date} onChange={setDate} max={todayISO()} aria-label="Day" />
        </div>
        <div className="flex w-56 flex-col gap-1.5">
          <span className="text-[13px] text-[var(--sd-muted)]">Herd</span>
          <Select value={herd} onValueChange={setHerd}>
            <SelectTrigger aria-label="Herd">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All herds</SelectItem>
              {herdNames.map((h) => (
                <SelectItem key={h.herd} value={h.herd}>
                  {h.herd_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {failure && <Notice tone="error">{failure}</Notice>}
      {!report && !failure && (
        <div className="flex items-center gap-2 text-[13px] text-[var(--sd-muted)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading the report…
        </div>
      )}

      {report && t && (
        <>
          <FigureRow>
            <Figure label="Planned" value={fmt(t.planned_kg)} unit="kg" />
            <Figure label="Fed" value={fmt(t.actual_kg)} unit="kg" />
            <Figure label="Below plan" value={String(t.below_plan)} unit="animals" />
            <Figure label="Above plan" value={String(t.above_plan)} unit="animals" />
            <Figure label="On plan" value={String(t.on_plan)} unit="animals" />
          </FigureRow>

          {report.herds.length === 0 ? (
            <Notice tone="info">No herd was fed on {report.date}.</Notice>
          ) : (
            <>
              {report.herds.map((h) => (
                <Card key={h.herd}>
                  <CardHeader>
                    <CardTitle>{h.herd_name}</CardTitle>
                    <CardDescription>
                      {h.head_count} head. Planned {fmt(h.planned_kg)} kg, fed {fmt(h.actual_kg)} kg
                      {h.amended ? ", amended" : ""}.
                      {h.draft_entries.length > 0 ? ` Waiting for stock: ${h.draft_entries.join(", ")}.` : ""}
                      {h.day_state === "half_fed" ? " Half fed: the second session is due." : ""}
                    </CardDescription>
                    <SessionChips sessions={h.sessions} />
                  </CardHeader>
                  <CardContent className="overflow-x-auto">
                    <table className="w-full text-[13px]">
                      <thead>
                        <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--sd-quiet)]">
                          <th className="py-1 pr-3 font-medium">Component</th>
                          <th className="py-1 pr-3 text-right font-medium">Planned</th>
                          <th className="py-1 text-right font-medium">Fed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {h.components.map((c) => (
                          <tr key={c.item_code} className="border-t border-[var(--sd-line)]">
                            <td className="py-1 pr-3">{c.item_name}</td>
                            <td className="py-1 pr-3 text-right tabular-nums">
                              {fmt(c.planned_kg)} {c.uom}
                            </td>
                            <td className="py-1 text-right tabular-nums">
                              {fmt(c.actual_kg)} {c.uom}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </CardContent>
                </Card>
              ))}

              <Card>
                <CardHeader>
                  <CardTitle>Animals</CardTitle>
                  <CardDescription>
                    Each animal is credited with an equal share of its herd&rsquo;s day.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ScrollTable tall>
                    <table className="w-full text-[13px]">
                      <thead>
                        <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--sd-quiet)]">
                          {["Animal", "Herd", "Planned kg", "Fed kg", "Difference kg", "Difference", "Appetite", "Last weight kg", "Weighed", "Gain kg/day"].map(
                            (c, i) => (
                              <th key={c} className={cn("py-1.5 pr-3 font-medium", STICKY_HEAD, i > 1 && "text-right")}>
                                {c}
                              </th>
                            ),
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {report.animals.map((a) => (
                          <tr key={a.animal} className="border-t border-[var(--sd-line)]">
                            <td className="py-1.5 pr-3">{a.tag}</td>
                            <td className="py-1.5 pr-3">{a.herd}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">{fmt(a.planned_kg)}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">{fmt(a.actual_kg)}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">{fmt(a.variance_kg)}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">{pctText(a.variance_pct)}</td>
                            <td className={cn("py-1.5 pr-3 text-right", TONE[a.appetite])}>
                              {APPETITE_LABEL[a.appetite]}
                            </td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">
                              {a.last_weight == null ? "—" : fmt(a.last_weight)}
                            </td>
                            <td className="py-1.5 pr-3 text-right">{a.last_weight_date ?? "—"}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">
                              {a.adg == null ? "—" : fmt(a.adg)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </ScrollTable>
                </CardContent>
              </Card>
            </>
          )}
        </>
      )}
    </Page>
  );
}
