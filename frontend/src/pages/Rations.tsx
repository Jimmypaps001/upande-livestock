import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Figure, FigureRow } from "@/components/Figure";
import { IngredientLines } from "@/components/feeding/IngredientLines";
import { Notice } from "@/components/feeding/Notice";
import { DatePicker } from "@/components/DatePicker";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { HEADER_PILL } from "@/components/header-controls";
import { Card, CardContent, CardDescription, CardHeader,
  CardHeaderRow,
  CardHeading,
  CardTools, CardTitle } from "@/components/ui/card";
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
  DEFAULT_MILK_WINDOW,
  groupByHerd,
  milkColumnLabel,
  milkCoverage,
  rationHistory,
  recipesUsed,
  type MilkWindow,
  type RationHistory,
  type RationRow,
} from "@/lib/rations";
import { cn, fmt } from "@/lib/utils";

/**
 * Rations — the record of what each herd was actually fed.
 *
 * One row per herd, per day, per recipe: the recipe the run cited, the
 * quantity mixed, how many head it was mixed for, and the milk recorded in
 * whichever window the reader chose.
 *
 * The milk figure is deliberately **beside** the ration and not derived from
 * it. There is no yield-per-kg column here and there should never be one: milk
 * comes from weeks of feeding, stage of lactation, weather and who was
 * milking, and a ratio on this page would read as a claim the data cannot
 * carry. The window control exists for the same reason — the farm says how
 * long it thinks the lag is, the page does not decide.
 *
 * The recipe is shown by name AND by BOM number. Three of this farm's BOMs are
 * all called "TMR Calves Meal"; the number is the only thing separating the
 * mix fed in April from the one fed in August.
 */

const WINDOW_HINTS: Record<string, string> = {
  same_day: "Milk recorded on the day the ration was mixed.",
  next_day: "Milk recorded the day after the ration was mixed.",
  plus_two: "Milk recorded two days after the ration was mixed.",
  avg_three:
    "The average of the days recorded between the day fed and two days after — over the days that were actually written down, not over three regardless.",
};

function Milk({ row }: { row: RationRow }) {
  if (row.milk_kg === null || row.milk_kg === undefined)
    return (
      <span className="text-[var(--sd-quiet)]" title="No milk recording in this window">
        not recorded
      </span>
    );
  return (
    <>
      {fmt(row.milk_kg)} <span className="text-[11px] text-[var(--sd-quiet)]">kg</span>
      {row.milk_days > 1 && (
        <span className="ml-1 text-[11px] text-[var(--sd-quiet)]">
          ({row.milk_days} days)
        </span>
      )}
    </>
  );
}

/** Row key stable enough to track which rows are expanded across a re-render
 *  — the same triple that already keys the `<tr>` itself. */
function rationRowKey(row: RationRow): string {
  return `${row.fed_on}::${row.herd}::${row.bom_no}`;
}

function RationTable({
  rows,
  milkHeading,
  showHerd,
}: {
  rows: RationRow[];
  milkHeading: string;
  showHerd: boolean;
}) {
  // Which rows are expanded to show their ingredients, kept local to this
  // table: a herd's card unmounting (the herd filter changed) should not
  // carry a stale set of open rows into the next one.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }
  const dataCols = showHerd ? 7 : 6;

  return (
    <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
      <table className="w-full min-w-[52rem] text-[13px]">
        <thead>
          <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
            <th className="w-8 px-2 py-2.5" aria-hidden="true" />
            <th className="px-3 py-2.5 font-medium">Fed on</th>
            {showHerd && <th className="px-3 py-2.5 font-medium">Herd</th>}
            <th className="px-3 py-2.5 font-medium">Recipe</th>
            <th className="px-3 py-2.5 text-right font-medium">Mixed</th>
            <th className="px-3 py-2.5 text-right font-medium">Head</th>
            <th className="px-3 py-2.5 font-medium">Mode</th>
            {/* Headed with the window that produced the number, never just
                "Milk" — the whole point of the control above. */}
            <th className="px-3 py-2.5 text-right font-medium">{milkHeading}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rationRowKey(row);
            const isOpen = expanded.has(key);
            return (
              <Fragment key={key}>
                <tr className="border-b border-[var(--sd-line-soft)] last:border-0">
                  <td className="px-2 py-2.5">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      aria-label={isOpen ? "Hide ingredients" : "Show ingredients"}
                      onClick={() => toggle(key)}
                      className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--sd-quiet)] transition-colors hover:bg-[var(--sd-bg-soft)] hover:text-[var(--sd-ink)]"
                    >
                      {isOpen ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </button>
                  </td>
                  <td className="px-3 py-2.5 tabular-nums text-[var(--sd-ink)]">{row.fed_on}</td>
                  {showHerd && (
                    <td className="px-3 py-2.5 text-[var(--sd-muted)]">{row.herd_label}</td>
                  )}
                  <td className="px-3 py-2.5 font-medium text-[var(--sd-ink)]">
                    {row.recipe}
                    {/* The BOM number is what tells one "TMR Calves Meal" from the
                        next, so it is on the page, not in a tooltip. */}
                    <div className="text-[11px] font-normal text-[var(--sd-quiet)]">
                      {row.bom_no}
                      {row.ration_kind ? ` · ${row.ration_kind.toLowerCase()}` : ""}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {fmt(row.qty)}{" "}
                    <span className="text-[11px] text-[var(--sd-quiet)]">{row.uom}</span>
                    {row.runs > 1 && (
                      <div className="text-[11px] text-[var(--sd-quiet)]">{row.runs} runs</div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--sd-muted)]">
                    {row.heads || <span className="text-[var(--sd-quiet)]">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-[var(--sd-muted)]">
                    {row.feed_mode || <span className="text-[var(--sd-quiet)]">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    <Milk row={row} />
                  </td>
                </tr>
                {isOpen && (
                  <tr className="border-b border-[var(--sd-line-soft)] bg-[var(--sd-bg-soft)] last:border-0">
                    <td />
                    <td colSpan={dataCols}>
                      <IngredientLines lines={row.lines} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Rations() {
  const [herd, setHerd] = useState<string>(ALL_HERDS);
  const [milkWindow, setMilkWindow] = useState<MilkWindow>(DEFAULT_MILK_WINDOW);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [data, setData] = useState<RationHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await rationHistory({ herd, fromDate, toDate, milkWindow, limit: 300 });
    setLoading(false);
    if (isError(r)) {
      setError(r.error);
      return;
    }
    setError(null);
    setData(r as RationHistory);
  }, [herd, fromDate, toDate, milkWindow]);

  useEffect(() => {
    load();
  }, [load]);

  const rows = data?.rows || [];
  // The server's own label, so the column heading and the figures under it can
  // never describe different days.
  const milkHeading = milkColumnLabel(data?.milk_window || milkWindow, data?.milk_window_label);
  const oneHerd = herd !== ALL_HERDS;
  const grouped = useMemo(() => groupByHerd(rows), [rows]);
  const recipes = useMemo(() => recipesUsed(rows), [rows]);
  const coverage = useMemo(() => milkCoverage(rows), [rows]);
  const herdOptions = data?.herds || [];

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Feeding" title="Rations">
        Every recipe a herd was actually fed, the day it went out and how much was mixed —
        read from the mix run itself, so a recipe changed today does not rewrite what was
        fed in April. The milk recorded nearby is shown next to it, in whichever window you
        choose. It is placed beside the ration, not divided by it: milk comes from weeks of
        feeding, not one day's mix.
      </PageHeading>

      {error && <Notice tone="error">{error}</Notice>}

      <Card>
        <CardHeaderRow className="flex-col items-stretch gap-3 sm:flex-col">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
            <CardHeading>
              <CardTitle>What was fed</CardTitle>
              <CardDescription>
                Narrow to one herd to read its recipe history in order, or leave it on
                every herd to see the farm's last few weeks.
              </CardDescription>
            </CardHeading>
            <CardTools>
              <Select value={herd} onValueChange={setHerd}>
                <SelectTrigger
                  id="rations-herd"
                  aria-label="Herd"
                  className={cn(HEADER_PILL, "max-w-[14rem]")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_HERDS}>Every herd</SelectItem>
                  {herdOptions.map((h) => (
                    <SelectItem key={h.herd} value={h.herd}>
                      {h.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={milkWindow}
                onValueChange={(v) => setMilkWindow(v as MilkWindow)}
              >
                <SelectTrigger
                  id="rations-window"
                  aria-label="Milk window"
                  className={cn(HEADER_PILL, "max-w-[15rem]")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(data?.windows || []).map((w) => (
                    <SelectItem key={w.value} value={w.value}>
                      {w.label}
                    </SelectItem>
                  ))}
                  {!data?.windows?.length && (
                    <SelectItem value={DEFAULT_MILK_WINDOW}>milk same day</SelectItem>
                  )}
                </SelectContent>
              </Select>
              <DatePicker
                id="rations-from"
                value={fromDate}
                max={toDate || undefined}
                onChange={setFromDate}
                aria-label="From"
              />
              <DatePicker
                id="rations-to"
                value={toDate}
                min={fromDate || undefined}
                onChange={setToDate}
                aria-label="To"
              />
              <RefreshButton onClick={load} loading={loading} label="the mix runs" />
            </CardTools>
          </div>
          <p className="text-[12px] text-[var(--sd-quiet)]">
            {WINDOW_HINTS[data?.milk_window || milkWindow]}
          </p>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-3">
          <FigureRow>
            <Figure label="Ration days" value={String(rows.length)} hint="herd × day × recipe" />
            <Figure label="Recipes used" value={String(recipes.length)} hint="distinct BOMs" />
            <Figure label="Herds fed" value={String(grouped.length)} />
            <Figure
              label="Days with milk"
              value={`${coverage.withMilk}/${coverage.total}`}
              hint="in this window"
            />
          </FigureRow>
          {/* An empty milk column is a recording gap, not a bad month, and the
              page has to say which. */}
          {coverage.total > 0 && coverage.withMilk < coverage.total && (
            <Notice tone="info">
              {coverage.total - coverage.withMilk} of {coverage.total} ration days have no
              milk recording in this window, so their milk column is blank rather than
              zero. Blank means nobody wrote a figure down — not that the herd gave
              nothing.
            </Notice>
          )}
          {data?.milk_visible === false && (
            <Notice tone="info">
              You are not permitted to read milk records, so the milk column is empty on
              every row. The rations themselves are unaffected.
            </Notice>
          )}
          {data?.truncated && (
            <Notice tone="info">
              Showing the most recent {data.limit} ration days. Set a From date to read
              further back.
            </Notice>
          )}
        </CardContent>
      </Card>

      {oneHerd && recipes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Recipes this herd has had</CardTitle>
            <CardDescription>
              Every distinct BOM fed to this herd in the range, most recent first. Counted
              by BOM number, not by name — this farm has several recipes sharing one item
              name.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
              <table className="w-full min-w-[36rem] text-[13px]">
                <thead>
                  <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
                    <th className="px-3 py-2.5 font-medium">Recipe</th>
                    <th className="px-3 py-2.5 text-right font-medium">Days fed</th>
                    <th className="px-3 py-2.5 text-right font-medium">Total mixed</th>
                    <th className="px-3 py-2.5 font-medium">Last fed</th>
                  </tr>
                </thead>
                <tbody>
                  {recipes.map((r) => (
                    <tr
                      key={r.bom_no}
                      className="border-b border-[var(--sd-line-soft)] last:border-0"
                    >
                      <td className="px-3 py-2.5 font-medium text-[var(--sd-ink)]">
                        {r.recipe}
                        <div className="text-[11px] font-normal text-[var(--sd-quiet)]">
                          {r.bom_no}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{r.days}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{fmt(r.qty)}</td>
                      <td className="px-3 py-2.5 tabular-nums text-[var(--sd-muted)]">
                        {r.last_fed}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {!rows.length ? (
        <Card>
          <CardContent className="py-6 text-[13px] text-[var(--sd-quiet)]">
            {loading
              ? "Reading the mix runs…"
              : "No ration was mixed for a herd in this range. Mix runs with no herd on them — bulk concentrate batches — are not ration records and are left out."}
          </CardContent>
        </Card>
      ) : oneHerd ? (
        <Card>
          <CardHeader>
            <CardTitle>{grouped[0]?.label || herd}</CardTitle>
            <CardDescription>Newest day first.</CardDescription>
          </CardHeader>
          <CardContent>
            <RationTable rows={grouped[0]?.rows || []} milkHeading={milkHeading} showHerd={false} />
          </CardContent>
        </Card>
      ) : (
        // Grouped by herd rather than one flat date list: a herd's history has
        // to read down the page in order, which is the question that was asked.
        grouped.map((group) => (
          <Card key={group.herd}>
            <CardHeader>
              <CardTitle>{group.label}</CardTitle>
              <CardDescription>
                {group.rows.length} ration {group.rows.length === 1 ? "day" : "days"}, newest
                first.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <RationTable rows={group.rows} milkHeading={milkHeading} showHerd={false} />
            </CardContent>
          </Card>
        ))
      )}
    </Page>
  );
}
