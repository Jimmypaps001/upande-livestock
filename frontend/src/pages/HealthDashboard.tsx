import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Stethoscope } from "lucide-react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { RowsSkeleton } from "@/components/Loading";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import { isError } from "@/lib/frappe";
import { getHealthOverview, type HealthOverview, type WardCase } from "@/lib/health";
import { cn, fmt } from "@/lib/utils";

/**
 * How the herd is, rather than a place to type what happened to one cow.
 *
 * THE HEALTH TAB WAS A FORM. Four screens for recording things and nothing that
 * answered "how is the herd?" — a farm could enter two hundred cases and never
 * see that mastitis was a third of them, or that March opened twice what
 * February did.
 *
 * Four things, because four is what fits in a glance and the rest is the
 * register next door: who is under treatment this morning, whether the farm is
 * catching up or falling behind, what she is being treated for, and where in
 * the farm it is happening.
 *
 * NOTHING HERE IS ESTIMATED. Where the record is silent — a treatment with no
 * response written against it, a case with no cost entered — the page says so
 * rather than filling the gap in with a plausible number.
 */
export function HealthDashboard({ onOpenCase }: { onOpenCase?: (name: string) => void }) {
  const [data, setData] = useState<HealthOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getHealthOverview();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setData(r);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const cost = data?.cost;

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Health">
        How the herd is. Who is being treated this morning, whether the farm is
        closing files as fast as it opens them, and what it is being treated for.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <FigureRow>
        <Figure
          loading={!data}
          label="Under treatment"
          value={String(data?.under_treatment ?? 0)}
          hint={data?.share != null ? `${data.share}% of ${data.herd_size} on the farm` : undefined}
        />
        <Figure
          loading={!data}
          label="Worth a look"
          value={String(data?.worrying.length ?? 0)}
          hint={
            data?.concern_days
              ? `open past ${data.concern_days} days, or gone quiet`
              : "the checks are switched off"
          }
        />
        <Figure
          loading={!data}
          label="Milk lost"
          value={cost?.lost_kg ? fmt(cost.lost_kg) : "—"}
          unit={cost?.lost_kg ? "kg" : undefined}
          hint="recorded against cases"
        />
        <Figure
          loading={!data}
          label="Treatment cost"
          value={cost?.treatment ? fmt(cost.treatment) : "—"}
          hint={
            cost && cost.cases
              ? `written down on ${cost.costed} of ${cost.cases} cases`
              : undefined
          }
        />
      </FigureRow>

      <div className="grid min-w-0 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Opened against closed</CardTitle>
              <CardDescription>
                Two lines, not one. A month that opened nine and closed nine is not
                the same farm as a month that did neither.
              </CardDescription>
            </CardHeading>
            <CardTools>
              <RefreshButton onClick={load} loading={loading} label="the figures" />
            </CardTools>
          </CardHeaderRow>
          <CardContent className="pt-0">
            {!data ? <RowsSkeleton rows={4} /> : <MonthBars months={data.months} />}
          </CardContent>
        </Card>

        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>What she is being treated for</CardTitle>
              <CardDescription>
                Ranked. The one figure here that changes what a farm does next
                season rather than this morning.
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="pt-0">
            {!data ? (
              <RowsSkeleton rows={4} />
            ) : !data.diagnoses.length ? (
              <p className="text-[13px] text-[var(--sd-muted)]">
                No cases in the window.
              </p>
            ) : (
              <Ranked
                rows={data.diagnoses.map((r) => ({
                  label: r.diagnosis || "Not said",
                  said: !!r.diagnosis,
                  value: r.cases,
                  hint:
                    r.open > 0
                      ? `${r.open} still open`
                      : r.confirmed
                        ? `${r.confirmed} confirmed`
                        : undefined,
                }))}
              />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>The ward</CardTitle>
              <CardDescription>
                Every file open right now, longest first. The flags are the farm's
                own lines — Settings, Health.
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="pt-0">
            {!data ? (
              <RowsSkeleton rows={5} />
            ) : !data.ward.length ? (
              <p className="text-[13px] text-[var(--sd-muted)]">
                Nobody is under treatment. Every file is closed.
              </p>
            ) : (
              <ul className="flex flex-col gap-1">
                {data.ward.map((c) => (
                  <Ward key={c.name} c={c} onOpen={onOpenCase} />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Where it is</CardTitle>
              <CardDescription>
                A herd is a shed, a ration and a water trough.
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="pt-0">
            {!data ? (
              <RowsSkeleton rows={4} />
            ) : (
              <Ranked
                rows={data.herds.map((h) => ({
                  label: h.herd || "No herd",
                  said: !!h.herd,
                  value: h.cases,
                  hint: h.open ? `${h.open} open` : undefined,
                }))}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}

function Ward({ c, onOpen }: { c: WardCase; onOpen?: (name: string) => void }) {
  const body = (
    <>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
          {c.animal_name || c.animal}
          <span className="ml-2 font-normal text-[11.5px] text-[var(--sd-quiet)]">
            {c.current_herd || "no herd"}
          </span>
        </span>
        <span className="truncate text-[11.5px] text-[var(--sd-muted)]">
          {c.provisional_diagnosis || c.case_status}
          {c.last_treatment_on ? ` · last treated ${c.last_treatment_on}` : " · never treated"}
        </span>
      </span>
      {c.concern && (
        <span
          title={c.concern.says}
          className="inline-flex shrink-0 items-center gap-1 text-[11.5px] text-[var(--sd-sev-moderate)]"
        >
          <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2} />
          {c.concern.kind === "stale" ? "quiet" : "long"}
        </span>
      )}
      <span className="w-16 shrink-0 text-right text-[12px] tabular-nums text-[var(--sd-quiet)]">
        {c.days_open ?? "—"} d
      </span>
    </>
  );
  return (
    <li>
      {onOpen ? (
        <button
          type="button"
          onClick={() => onOpen(c.name)}
          className="flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-2 py-2 text-left transition-colors hover:bg-[var(--sd-bg-soft)]"
        >
          {body}
        </button>
      ) : (
        <span className="flex w-full items-center gap-3 px-2 py-2">{body}</span>
      )}
    </li>
  );
}

const MONTH_H = 150;

/**
 * Opened and closed, month by month, as paired bars.
 *
 * Paired rather than stacked: stacking would make a busy month and a month that
 * cleared its backlog the same height, and the difference between those two is
 * the whole question.
 */
function MonthBars({ months }: { months: { month: string; opened: number; closed: number }[] }) {
  const top = Math.max(...months.map((m) => Math.max(m.opened, m.closed)), 1);
  const colW = 34;
  const width = Math.max(months.length * colW, 200);

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <svg
          width={width}
          height={MONTH_H + 20}
          viewBox={`0 0 ${width} ${MONTH_H + 20}`}
          role="img"
          aria-label="Cases opened and closed by month"
        >
          <line
            x1={0} y1={MONTH_H} x2={width} y2={MONTH_H}
            stroke="var(--sd-line)" strokeWidth={1}
          />
          {months.map((m, i) => {
            const x = i * colW;
            const h = (n: number) => (n / top) * (MONTH_H - 12);
            return (
              <g key={m.month}>
                <rect
                  x={x + 6} y={MONTH_H - h(m.opened)} width={9}
                  height={Math.max(m.opened ? 2 : 0, h(m.opened))}
                  rx={2} fill="var(--sd-sev-moderate)"
                >
                  <title>{`${m.month}: ${m.opened} opened`}</title>
                </rect>
                <rect
                  x={x + 17} y={MONTH_H - h(m.closed)} width={9}
                  height={Math.max(m.closed ? 2 : 0, h(m.closed))}
                  rx={2} fill="var(--sd-data-green)"
                >
                  <title>{`${m.month}: ${m.closed} closed`}</title>
                </rect>
                <text
                  x={x + 17} y={MONTH_H + 14}
                  textAnchor="middle"
                  className="fill-[var(--sd-quiet)] text-[9.5px]"
                >
                  {m.month.slice(5)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--sd-quiet)]">
        <Key tone="var(--sd-sev-moderate)" label="Opened" />
        <Key tone="var(--sd-data-green)" label="Closed" />
      </div>
    </div>
  );
}

function Key({ tone, label }: { tone: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-[2px]" style={{ background: tone }} />
      {label}
    </span>
  );
}

/** A ranked list drawn as bars, because the order is the message. */
function Ranked({
  rows,
}: {
  rows: { label: string; value: number; hint?: string; said?: boolean }[];
}) {
  const top = Math.max(...rows.map((r) => r.value), 1);
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map((r) => (
        <li key={r.label} className="flex flex-col gap-1">
          <span className="flex items-baseline justify-between gap-3 text-[12.5px]">
            <span
              className={cn(
                "truncate",
                r.said === false ? "italic text-[var(--sd-quiet)]" : "text-[var(--sd-ink)]",
              )}
            >
              {r.label}
            </span>
            <span className="shrink-0 tabular-nums text-[var(--sd-muted)]">
              {r.value}
              {r.hint ? <span className="ml-2 text-[var(--sd-quiet)]">{r.hint}</span> : null}
            </span>
          </span>
          <span className="h-1.5 overflow-hidden rounded-full bg-[var(--sd-bg-soft)]">
            <span
              className="block h-full rounded-full bg-[var(--sd-data-cyan)]"
              style={{ width: `${Math.max(3, (r.value / top) * 100)}%` }}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}
