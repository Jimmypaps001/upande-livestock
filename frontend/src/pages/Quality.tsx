import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, FlaskConical } from "lucide-react";
import { DatePicker } from "@/components/DatePicker";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
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
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/Toast";
import { isError } from "@/lib/frappe";
import {
  getQualityOptions,
  recordMilkQuality,
  type PendingRecording,
  type QualityOptions,
} from "@/lib/quality";
import { cn, fmt, todayISO } from "@/lib/utils";

/**
 * The lab step.
 *
 * A creamery docket comes back a day or two after the milk went out, and until
 * it does the recording is complete in every way that posts — the stock moved,
 * the revenue is booked — and incomplete in the one way that does not. This
 * page is that gap, made visible and worked through.
 *
 * It exists whether or not the farm captures quality at milking: a figure can
 * always be missing, and a page that appeared only in one mode would strand
 * every recording taken on a handset, which never captures quality at all.
 */
export function Quality() {
  const [data, setData] = useState<QualityOptions | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<PendingRecording | null>(null);
  const [scc, setScc] = useState("");
  const [fat, setFat] = useState("");
  const [protein, setProtein] = useState("");
  const [testedOn, setTestedOn] = useState(todayISO());
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getQualityOptions();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setData(r);
    setActive((current) =>
      current && r.pending.some((p) => p.name === current.name) ? current : r.pending[0] ?? null,
    );
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const overCeiling = useMemo(() => {
    const value = Number(scc);
    return !!(data?.scc_ceiling && value > data.scc_ceiling);
  }, [scc, data]);

  async function save() {
    if (!active) return;
    setSaving(true);
    const r = await recordMilkQuality({
      recording: active.name,
      bulk_scc: scc ? Number(scc) : undefined,
      fat_percent: fat ? Number(fat) : undefined,
      protein_percent: protein ? Number(protein) : undefined,
      lab_test_date: testedOn,
    });
    setSaving(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast(
      r.over_ceiling
        ? `Filed against ${r.name}. The cell count is above the farm's ceiling — worth a look at the herd.`
        : `Filed against ${r.name}.`,
    );
    setScc("");
    setFat("");
    setProtein("");
    void load();
  }

  const pending = data?.pending ?? [];
  const recent = data?.recent ?? [];
  const flagged = recent.filter((r) => r.over_ceiling).length;

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Milking" title="Quality">
        The bulk tank figures that come back from the creamery, filed against the
        milking they belong to. Nothing here moves stock or money — those posted
        when the milking was recorded.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      {data && (
        <Notice tone="info">
          {data.mode === "At milking"
            ? "This farm records quality at milking. What is listed here was left blank at the time, or came in from a handset."
            : "This farm records quality afterwards. Every milking arrives here for its figures."}
          {data.required_in_lab
            ? " A recording stays on this list until a figure is entered."
            : " Nothing is chased — the list is for reference."}
        </Notice>
      )}

      <FigureRow>
        <Figure label="Awaiting quality" value={String(pending.length)} hint="last 60 days" />
        <Figure label="Filed" value={String(recent.length)} hint="last 60 days" />
        <Figure
          label="Over the ceiling"
          value={String(flagged)}
          hint={data?.scc_ceiling ? `above ${fmt(data.scc_ceiling)} × 1000 cells/ml` : "no ceiling set"}
        />
        <Figure
          label="Captured"
          value={data?.mode === "Afterwards" ? "Afterwards" : "At milking"}
          hint="set in Settings"
        />
      </FigureRow>

      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Awaiting quality</CardTitle>
              <CardDescription>Oldest milking at the bottom.</CardDescription>
            </CardHeading>
            <CardTools>
              <RefreshButton onClick={load} loading={loading} label="the outstanding list" />
            </CardTools>
          </CardHeaderRow>
          <CardContent className="pt-0">
            {!pending.length ? (
              <p className="text-[13px] text-[var(--sd-muted)]">
                Nothing outstanding. Every milking in the last sixty days has its figures.
              </p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {pending.map((p) => {
                  const on = p.name === active?.name;
                  return (
                    <li key={p.name}>
                      <button
                        type="button"
                        onClick={() => setActive(p)}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
                          // Inside a card: fill marks the selection, not lift.
                          on ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
                        )}
                      >
                        <FlaskConical
                          className="h-4 w-4 shrink-0 text-[var(--sd-quiet)]"
                          strokeWidth={1.75}
                        />
                        <span className="flex min-w-0 flex-1 flex-col">
                          <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                            {p.herd}
                          </span>
                          <span className="text-[11.5px] tabular-nums text-[var(--sd-muted)]">
                            {p.recording_date}
                            {p.milking_time ? ` · ${String(p.milking_time).slice(0, 5)}` : ""}
                          </span>
                        </span>
                        <span className="shrink-0 text-[11.5px] tabular-nums text-[var(--sd-quiet)]">
                          {fmt(p.net_yield_kg)} kg
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>{active ? `File a result` : "Nothing selected"}</CardTitle>
              <CardDescription>
                {active
                  ? `${active.herd} · ${active.recording_date} · ${fmt(active.net_yield_kg)} kg sellable`
                  : "Pick a milking on the left."}
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-4 pt-0">
            {!active ? (
              <p className="text-[13px] text-[var(--sd-muted)]">
                Results are filed one milking at a time, against the session they came
                from — a bulk tank figure belongs to a tank, not to a day.
              </p>
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="q-scc">Bulk tank SCC (× 1000 cells/ml)</Label>
                    <Input
                      id="q-scc"
                      type="number"
                      min={0}
                      step="any"
                      value={scc}
                      onChange={(e) => setScc(e.target.value)}
                      className={overCeiling ? "border-[var(--sd-sev-critical)]" : undefined}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="q-date">Lab test date</Label>
                    <DatePicker
                      id="q-date"
                      value={testedOn}
                      max={todayISO()}
                      onChange={setTestedOn}
                      aria-label="Lab test date"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="q-fat">Fat %</Label>
                    <Input
                      id="q-fat"
                      type="number"
                      min={0}
                      step="any"
                      value={fat}
                      onChange={(e) => setFat(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="q-protein">Protein %</Label>
                    <Input
                      id="q-protein"
                      type="number"
                      min={0}
                      step="any"
                      value={protein}
                      onChange={(e) => setProtein(e.target.value)}
                    />
                  </div>
                </div>

                {overCeiling && (
                  <Notice tone="error">
                    <span className="inline-flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4" />
                      {fmt(Number(scc))} is above the farm&apos;s ceiling of{" "}
                      {fmt(data?.scc_ceiling ?? 0)}. It will still be filed — the figure is
                      the figure — and flagged on the list below.
                    </span>
                  </Notice>
                )}

                <p className="text-[12px] text-[var(--sd-quiet)]">
                  One figure is enough. Saving an empty result is refused, because it
                  would clear the chase without answering it.
                </p>

                <div className="flex flex-wrap items-center gap-3">
                  <Button onClick={save} disabled={saving || !data?.can_write}>
                    {saving ? "Filing…" : "File the result"}
                  </Button>
                  {!data?.can_write && (
                    <span className="text-[12px] text-[var(--sd-muted)]">
                      You may read these but not file them.
                    </span>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Filed results</CardTitle>
            <CardDescription>The last sixty days, newest first.</CardDescription>
          </CardHeading>
        </CardHeaderRow>
        <CardContent className="pt-0">
          {!recent.length ? (
            <p className="text-[13px] text-[var(--sd-muted)]">Nothing filed yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] border-collapse text-[13px]">
                <thead>
                  <tr className="border-b border-[var(--sd-line)] text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
                    <th className="py-2 pr-3">Herd</th>
                    <th className="py-2 pr-3">Milked</th>
                    <th className="py-2 pr-3 text-right">SCC</th>
                    <th className="py-2 pr-3 text-right">Fat %</th>
                    <th className="py-2 pr-3 text-right">Protein %</th>
                    <th className="py-2 text-right">Tested</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((r) => (
                    <tr key={r.name} className="border-b border-[var(--sd-line-soft)] last:border-0">
                      <td className="py-2 pr-3 text-[var(--sd-ink)]">{r.herd}</td>
                      <td className="py-2 pr-3 tabular-nums text-[var(--sd-muted)]">
                        {r.recording_date}
                      </td>
                      <td
                        className={cn(
                          "py-2 pr-3 text-right tabular-nums",
                          r.over_ceiling
                            ? "font-semibold text-[var(--sd-sev-critical)]"
                            : "text-[var(--sd-ink)]",
                        )}
                      >
                        {r.bulk_scc ? fmt(r.bulk_scc) : "—"}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-[var(--sd-muted)]">
                        {r.fat_percent ? fmt(r.fat_percent) : "—"}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-[var(--sd-muted)]">
                        {r.protein_percent ? fmt(r.protein_percent) : "—"}
                      </td>
                      <td className="py-2 text-right tabular-nums text-[var(--sd-quiet)]">
                        {r.lab_test_date || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
