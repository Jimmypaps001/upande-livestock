import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { HEADER_PILL } from "@/components/header-controls";
import { RowsSkeleton } from "@/components/Loading";
import { Page, PageHeading } from "@/components/PageShell";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { isError } from "@/lib/frappe";
import {
  DEFAULT_PERIOD_DAYS,
  PERIOD_OPTIONS,
  formatAdg,
  formatWeight,
  getBullPerformance,
  isHighlighted,
  listPerformanceHerds,
  sortRows,
  type PerformanceHerd,
  type PerformanceView,
} from "@/lib/performance";
import { cn } from "@/lib/utils";

/**
 * Bull Performance: the herd ranked by how fast each animal is putting on
 * weight over the chosen period.
 *
 * The ranking is by gain over the period, because that is what the next sale
 * or move is decided on. The lifetime figure sits beside the herd's target so
 * a bull that has always been slow reads differently from one that has just
 * stalled. An animal without two weighings in the period is listed last with
 * the words, not a zero.
 */
export function Performance() {
  const [herds, setHerds] = useState<PerformanceHerd[]>([]);
  const [herd, setHerd] = useState("");
  const [period, setPeriod] = useState<number>(DEFAULT_PERIOD_DAYS);
  const [view, setView] = useState<PerformanceView | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);

  // The herd list first; the first herd is chosen once it arrives.
  useEffect(() => {
    let live = true;
    (async () => {
      const r = await listPerformanceHerds();
      if (!live) return;
      if (!Array.isArray(r)) {
        setFailure(r.error);
        setLoading(false);
        return;
      }
      const list = r;
      setHerds(list);
      if (list.length) setHerd((h) => h || list[0].herd);
      else setLoading(false);
    })();
    return () => {
      live = false;
    };
  }, []);

  // Only the newest request may write: a slow answer for the herd or period
  // you have already left must not land on top of the one you are looking at.
  const latest = useRef(0);
  const load = useCallback(async () => {
    if (!herd) return;
    const mine = ++latest.current;
    setLoading(true);
    const r = await getBullPerformance(herd, period);
    if (mine !== latest.current) return;
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setView(r as PerformanceView);
  }, [herd, period]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(() => sortRows(view?.rows || []), [view]);
  const target = view?.target_adg_kg ?? null;
  const showing = !!view && view.herd === herd && view.period_days === period;

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Beef" title="Bull Performance">
        Each animal in a herd ranked by the weight it has put on over the period. Rows
        shaded amber are gaining less than the herd's target.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <Card>
        <CardHeaderRow className="flex-col items-stretch gap-3 sm:flex-col">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
            <CardHeading>
              <CardTitle>{herd || "Choose a herd"}</CardTitle>
              <CardDescription>
                {target !== null && showing
                  ? `Target gain ${formatAdg(target)}.`
                  : "No target gain is set for this herd."}
              </CardDescription>
            </CardHeading>
            <CardTools>
              <Select value={herd} onValueChange={setHerd}>
                <SelectTrigger
                  id="perf-herd"
                  aria-label="Herd"
                  className={cn(HEADER_PILL, "max-w-[14rem]")}
                >
                  <SelectValue placeholder="Choose a herd…" />
                </SelectTrigger>
                <SelectContent>
                  {herds.map((h) => (
                    <SelectItem key={h.herd} value={h.herd}>
                      {h.herd} ({h.head_count})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={String(period)} onValueChange={(v) => setPeriod(Number(v))}>
                <SelectTrigger id="perf-period" aria-label="Period" className={HEADER_PILL}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PERIOD_OPTIONS.map((d) => (
                    <SelectItem key={d} value={String(d)}>
                      Last {d} days
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <RefreshButton onClick={load} loading={loading} label="the ranking" />
            </CardTools>
          </div>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-3">
          <FigureRow>
            <Figure
              label="Head"
              value={showing ? String(view.summary.head_count) : "—"}
              loading={loading && !showing}
            />
            <Figure
              label="Average weight"
              value={showing ? formatWeight(view.summary.avg_weight_kg) : "—"}
              loading={loading && !showing}
            />
            <Figure
              label="Average gain"
              value={
                showing && view.summary.avg_period_adg !== null
                  ? view.summary.avg_period_adg.toFixed(2)
                  : "—"
              }
              unit="kg/day"
              hint={`over ${period} days`}
              loading={loading && !showing}
            />
          </FigureRow>

          {loading && !showing ? (
            <RowsSkeleton rows={6} />
          ) : rows.length === 0 ? (
            <p className="px-1 py-6 text-center text-[13px] text-[var(--sd-muted)]">
              {failure
                ? "The ranking could not be loaded."
                : herd
                  ? "No animals in this herd."
                  : "No beef herds to rank yet."}
            </p>
          ) : (
            <div
              className={cn(
                "overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] transition-opacity",
                loading && "opacity-60",
              )}
            >
              <table className="w-full min-w-[52rem] text-[13px]">
                <thead>
                  <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
                    <th className="px-3 py-2.5 font-medium">Rank</th>
                    <th className="px-3 py-2.5 font-medium">Tag</th>
                    <th className="px-3 py-2.5 text-right font-medium">Latest weight</th>
                    <th className="px-3 py-2.5 text-right font-medium">Since weighing</th>
                    <th className="px-3 py-2.5 text-right font-medium">Gain, period</th>
                    <th className="px-3 py-2.5 text-right font-medium">Gain in herd</th>
                    <th className="px-3 py-2.5 text-right font-medium">Lifetime gain</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const hot = isHighlighted(row);
                    return (
                      <tr
                        key={row.animal}
                        data-below-target={hot ? "true" : undefined}
                        className={cn(
                          "border-b border-[var(--sd-line-soft)] last:border-0",
                          hot && "bg-[var(--sd-amber-bg)]",
                        )}
                      >
                        <td className="px-3 py-2.5 tabular-nums text-[var(--sd-muted)]">
                          {row.rank ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-medium tabular-nums text-[var(--sd-ink)]">
                          {row.label || row.animal}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {formatWeight(row.latest_weight_kg)}
                          {row.latest_weight_date && (
                            <div className="text-[11px] text-[var(--sd-quiet)]">
                              {row.latest_weight_date}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-[var(--sd-muted)]">
                          {row.days_since_weighing === null
                            ? "—"
                            : `${row.days_since_weighing} d`}
                        </td>
                        <td
                          className={cn(
                            "px-3 py-2.5 text-right tabular-nums",
                            row.period_adg === null
                              ? "text-[var(--sd-quiet)]"
                              : "font-medium text-[var(--sd-ink)]",
                          )}
                        >
                          {formatAdg(row.period_adg)}
                          {hot && (
                            <div className="text-[11px] font-medium text-[var(--sd-amber)]">
                              Below target
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-[var(--sd-muted)]">
                          {row.herd_adg === null ? "—" : formatAdg(row.herd_adg)}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-[var(--sd-muted)]">
                          {row.lifetime_adg === null ? "—" : formatAdg(row.lifetime_adg)}
                          {target !== null && (
                            <div className="text-[11px] text-[var(--sd-quiet)]">
                              target {formatAdg(target)}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                {showing && (
                  <tfoot>
                    <tr
                      data-testid="herd-summary-row"
                      className="border-t border-[var(--sd-line)] bg-[var(--sd-bg-soft)] font-medium text-[var(--sd-ink)]"
                    >
                      <td className="px-3 py-2.5" />
                      <td className="px-3 py-2.5">Herd · {view.summary.head_count} head</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {formatWeight(view.summary.avg_weight_kg)}
                      </td>
                      <td className="px-3 py-2.5" />
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {formatAdg(view.summary.avg_period_adg)}
                      </td>
                      <td className="px-3 py-2.5" />
                      <td className="px-3 py-2.5" />
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
