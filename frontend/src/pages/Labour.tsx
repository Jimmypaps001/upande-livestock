import { useCallback, useEffect, useRef, useState } from "react";
import { DatePicker } from "@/components/DatePicker";
import { Notice } from "@/components/feeding/Notice";
import { RowsSkeleton } from "@/components/Loading";
import { Page, PageHeading } from "@/components/PageShell";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeaderRow,
  CardHeading,
  CardTitle,
  CardTools,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  fmtMoney,
  getDailyLabour,
  labourAmount,
  saveDailyLabour,
  type LabourDay,
  type LabourRow,
} from "@/lib/costing";
import { isError } from "@/lib/frappe";
import { todayISO } from "@/lib/utils";

const HEAD_ROW =
  "border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]";

/**
 * Daily Labour: who worked today, entered by the feedlot manager.
 *
 * One row per category; the day rate is already filled from Settings, so an
 * ordinary day is three numbers. A rate typed here is that day's rate and wins
 * over the setting. Cost per animal spreads the day's total over every animal
 * on the farm.
 */
export function Labour() {
  const today = todayISO();
  const toast = useToast();
  const [date, setDate] = useState(today);
  const [day, setDay] = useState<LabourDay | null>(null);
  const [rows, setRows] = useState<LabourRow[]>([]);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const latest = useRef(0);
  const load = useCallback(async (on: string) => {
    const mine = ++latest.current;
    setLoading(true);
    const r = await getDailyLabour(on);
    if (mine !== latest.current) return;
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      setDay(null);
      return;
    }
    const d = r as LabourDay;
    setFailure(null);
    setDay(d);
    // Every category on screen, even one the saved day had no line for.
    const have = new Set(d.rows.map((x) => x.category));
    setRows([
      ...d.rows,
      ...d.categories
        .filter((c) => !have.has(c))
        .map((c) => ({ category: c, workers: 0, day_rate: d.default_rates[c] ?? null })),
    ]);
    setNotes(d.notes || "");
  }, []);

  useEffect(() => {
    void load(date);
  }, [date, load]);

  const defaults = day?.default_rates || {};
  const total = rows.reduce((s, r) => s + labourAmount(r, defaults), 0);
  const workers = rows.reduce((s, r) => s + Math.max(0, Math.trunc(Number(r.workers) || 0)), 0);
  const canWrite = !!day?.can_write;

  const edit = (i: number, patch: Partial<LabourRow>) =>
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const save = async () => {
    setSaving(true);
    const r = await saveDailyLabour({
      date,
      notes,
      rows: rows.map((x) => ({
        category: x.category,
        workers: Math.max(0, Math.trunc(Number(x.workers) || 0)),
        day_rate: x.day_rate === null || x.day_rate === undefined || String(x.day_rate) === "" ? null : Number(x.day_rate),
        notes: x.notes || "",
      })),
    });
    setSaving(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast(`Labour for ${date} saved: KES ${fmtMoney(r.total_amount)}.`, "ok");
    void load(date);
  };

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Costs" title="Daily Labour">
        How many worked on the farm each day, and at what rate. The day's total is spread over
        every animal on the farm in Cost per animal.
      </PageHeading>
      {failure && <Notice tone="error">{failure}</Notice>}

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>{day?.saved ? "Entered" : "Not entered yet"}</CardTitle>
            <CardDescription>
              The rate is filled from Settings; change it only for a day that was paid differently.
            </CardDescription>
          </CardHeading>
          <CardTools>
            <DatePicker value={date} onChange={setDate} max={today} aria-label="Labour date" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-4">
          {loading && !day ? (
            <RowsSkeleton rows={3} />
          ) : (
            <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
              <table className="w-full min-w-[36rem] text-[13px]" data-testid="labour-rows">
                <thead>
                  <tr className={HEAD_ROW}>
                    <th className="px-3 py-2.5 font-medium">Category</th>
                    <th className="px-3 py-2.5 text-right font-medium">Workers</th>
                    <th className="px-3 py-2.5 text-right font-medium">Day rate (KES)</th>
                    <th className="px-3 py-2.5 text-right font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.category} className="border-b border-[var(--sd-line-soft)] last:border-0">
                      <td className="px-3 py-2">{r.category}</td>
                      <td className="px-3 py-2 text-right">
                        <Input
                          aria-label={`${r.category} workers`}
                          type="number"
                          min={0}
                          step={1}
                          inputMode="numeric"
                          className="ml-auto h-9 w-24 text-right tabular-nums"
                          value={String(r.workers ?? 0)}
                          disabled={!canWrite}
                          onChange={(e) => edit(i, { workers: Number(e.target.value) })}
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Input
                          aria-label={`${r.category} day rate`}
                          type="number"
                          min={0}
                          inputMode="decimal"
                          className="ml-auto h-9 w-28 text-right tabular-nums"
                          placeholder={String(defaults[r.category] ?? "")}
                          value={r.day_rate === null || r.day_rate === undefined ? "" : String(r.day_rate)}
                          disabled={!canWrite}
                          onChange={(e) =>
                            edit(i, { day_rate: e.target.value === "" ? null : Number(e.target.value) })
                          }
                        />
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums" data-cell="amount">
                        {fmtMoney(labourAmount(r, defaults))}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-[var(--sd-line)] font-medium">
                    <td className="px-3 py-2.5">Total</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{workers}</td>
                    <td />
                    <td className="px-3 py-2.5 text-right tabular-nums" data-cell="total">
                      {fmtMoney(total)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
          <Input
            aria-label="Notes"
            placeholder="Notes (optional)"
            value={notes}
            disabled={!canWrite}
            onChange={(e) => setNotes(e.target.value)}
          />
          {day && !canWrite && (
            <Notice tone="info">Only a Livestock Manager can enter labour. You can see what was entered.</Notice>
          )}
          <div className="flex justify-end">
            <Button onClick={save} disabled={!canWrite || saving || loading}>
              {saving ? "Saving…" : "Save the day's labour"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {day && day.recent.length > 0 && (
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Days entered</CardTitle>
            </CardHeading>
          </CardHeaderRow>
          <CardContent>
            <ul className="flex flex-col divide-y divide-[var(--sd-line-soft)] text-[13px]">
              {day.recent.map((r) => (
                <li key={r.name}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between px-2 py-2 text-left hover:bg-[var(--sd-bg-soft)]"
                    onClick={() => setDate(r.date)}
                  >
                    <span className="tabular-nums">{r.date}</span>
                    <span className="tabular-nums text-[var(--sd-muted)]">
                      {r.workers} workers · KES {fmtMoney(r.amount)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </Page>
  );
}
