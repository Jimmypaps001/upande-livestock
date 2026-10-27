import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, HeartPulse } from "lucide-react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { STICKY_HEAD, ScrollTable } from "@/components/ScrollTable";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { isError } from "@/lib/frappe";
import {
  getEventsView, getOpenCases, getReportsView,
  type EventsView, type OpenCasesView, type ReportsView,
} from "@/lib/events";
import { cn, fmt } from "@/lib/utils";

/**
 * The three screens that only read.
 *
 * Everything else in this app records something. These are the ones somebody
 * opens to find out — what happened, how the farm is doing,
 * what is still being treated — and their whole job is to be legible at a
 * glance and honest about what they do not know.
 */

function useView<T>(load: () => Promise<{ error?: string } | T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    const r = await load();
    setLoading(false);
    if (isError(r as never)) {
      setFailure((r as { error: string }).error);
      return;
    }
    setFailure(null);
    setData(r as T);
  }, [load]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, failure, refresh };
}

export function Events() {
  const load = useCallback(() => getEventsView(), []);
  const { data, loading, failure, refresh } = useView<EventsView>(load);
  const [type, setType] = useState("");
  const [term, setTerm] = useState("");

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const q = term.trim().toLowerCase();
    return all.filter(
      (r) =>
        (!type || r.event_type === type) &&
        (!q ||
          [r.animal || "", r.event_type || "", r.current_herd || "", r.new_herd || ""].some((f) =>
            f.toLowerCase().includes(q),
          )),
    );
  }, [data, type, term]);

  const types = data?.filters?.types ?? [];

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Herd" title="Events">
        Everything that has happened to the herd lately, newest first. Each row
        is a record somebody made, not a summary of one.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}
      {data?.error && <Notice tone="error">{data.error}</Notice>}

      <FigureRow>
        <Figure label="Recorded" value={String(data?.summary?.total ?? 0)} hint="recent events" />
        <Figure label="Kinds" value={String(types.length)} hint="of event" />
        <Figure label="Showing" value={String(rows.length)} hint={type || "everything"} />
      </FigureRow>

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Recent events</CardTitle>
            <CardDescription>Filter by kind, or search for an animal.</CardDescription>
          </CardHeading>
          <CardTools>
            <RefreshButton onClick={refresh} loading={loading} label="the events" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-3 pt-0">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Animal, herd…"
              aria-label="Search the events"
              className="h-9 max-w-[240px] rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] text-[13px]"
            />
            <div className="flex flex-wrap items-center gap-1 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] p-0.5">
              {["", ...types].map((t) => (
                <button
                  key={t || "all"}
                  type="button"
                  onClick={() => setType(t)}
                  className={cn(
                    "rounded-[var(--sd-radius-pill)] px-2.5 py-1 text-[11.5px] font-medium transition-all",
                    t === type
                      ? "bg-[var(--sd-card)] text-[var(--sd-ink)] shadow-[var(--sd-shadow-1)]"
                      : "text-[var(--sd-muted)] hover:text-[var(--sd-ink)]",
                  )}
                >
                  {t || "All"}
                </button>
              ))}
            </div>
          </div>

          {!rows.length ? (
            <p className="text-[13px] text-[var(--sd-muted)]">Nothing matches.</p>
          ) : (
            <ScrollTable tall>
              <table className="w-full min-w-[560px] text-[12.5px]">
                <thead className={STICKY_HEAD}>
                  <tr className="text-left text-[10.5px] uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
                    <th className="py-2 pr-3 font-medium">When</th>
                    <th className="py-2 pr-3 font-medium">What</th>
                    <th className="py-2 pr-3 font-medium">Animal</th>
                    <th className="py-2 font-medium">Herd</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.name} className="border-t border-[var(--sd-line)]">
                      <td className="py-2.5 pr-3 tabular-nums text-[var(--sd-muted)]">
                        {r.event_date || "—"}
                      </td>
                      <td className="py-2.5 pr-3 text-[var(--sd-ink)]">{r.event_type || "—"}</td>
                      <td className="py-2.5 pr-3 tabular-nums text-[var(--sd-muted)]">
                        {r.animal || "—"}
                      </td>
                      <td className="py-2.5 text-[var(--sd-muted)]">
                        {r.new_herd && r.new_herd !== r.current_herd
                          ? `${r.current_herd || "—"} → ${r.new_herd}`
                          : r.current_herd || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollTable>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}

export function Reports() {
  const load = useCallback(() => getReportsView(), []);
  const { data, loading, failure, refresh } = useView<ReportsView>(load);
  const h = data?.health ?? {};
  const r = data?.reproduction ?? {};
  const herds = data?.herds ?? [];
  const biggest = Math.max(1, ...herds.map((x) => x.animals));

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Herd" title="Reports">
        The month against the one before it. Head counts are counted the way the
        herd records and the feed run count them — animals that have left are
        not standing in a herd.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}
      {data?.error && <Notice tone="error">{data.error}</Notice>}

      <FigureRow>
        <Figure label="Open cases" value={String(h.open_cases ?? 0)}
                hint={`${h.open_rate ?? 0}% of the herd`} />
        <Figure label="Births" value={String(r.births_month ?? 0)} hint="this month" />
      </FigureRow>

      <div className="grid min-w-0 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Where the animals are</CardTitle>
              <CardDescription>The eight largest herds.</CardDescription>
            </CardHeading>
            <CardTools>
              <RefreshButton onClick={refresh} loading={loading} label="the figures" />
            </CardTools>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-2 pt-0">
            {!herds.length ? (
              <p className="text-[13px] text-[var(--sd-muted)]">No herd holds an animal.</p>
            ) : (
              herds.map((x) => (
                <div key={x.name} className="flex items-center gap-3">
                  <span className="w-[46%] shrink-0 truncate text-[12.5px] text-[var(--sd-ink)]">
                    {x.name}
                  </span>
                  <span
                    className="h-2.5 rounded-full bg-[var(--sd-series-2)]"
                    style={{ width: `${Math.max(4, (x.animals / biggest) * 46)}%` }}
                    aria-hidden
                  />
                  <span className="shrink-0 text-[12px] tabular-nums text-[var(--sd-muted)]">
                    {x.animals}
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Reproduction and health</CardTitle>
              <CardDescription>Where the herd stands today.</CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-1 pt-0">
            <Line icon={<Activity className="h-3.5 w-3.5" strokeWidth={2} />} label="Carrying" value={r.pregnant ?? 0} />
            <Line icon={<Activity className="h-3.5 w-3.5" strokeWidth={2} />} label="Served, awaiting a check" value={r.served ?? 0} />
            <Line icon={<Activity className="h-3.5 w-3.5" strokeWidth={2} />} label="Open" value={r.open ?? 0} />
            <Line icon={<HeartPulse className="h-3.5 w-3.5" strokeWidth={2} />} label="Cases opened this month" value={h.cases_month ?? 0} />
            <Line icon={<HeartPulse className="h-3.5 w-3.5" strokeWidth={2} />} label="Animals on the farm" value={h.active_animals ?? 0} />
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}

function Line({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-[var(--sd-line)] px-1 py-2 text-[12.5px] first:border-t-0">
      <span className="flex items-center gap-2 text-[var(--sd-muted)]">
        <span className="text-[var(--sd-quiet)]">{icon}</span>
        {label}
      </span>
      <span className="tabular-nums font-medium text-[var(--sd-ink)]">{fmt(value)}</span>
    </div>
  );
}
