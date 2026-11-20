import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, FlaskConical } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { STICKY_HEAD, ScrollTable } from "@/components/ScrollTable";
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
import { Picker } from "@/components/ui/picker";
import { useToast } from "@/components/Toast";
import { isError, uploadFile } from "@/lib/frappe";
import {
  CHECK_LABELS,
  emptyForm,
  batchFields,
  formProblem,
  getMilkBatches,
  getQualityTestOptions,
  getQualityTests,
  payloadFrom,
  previewChecks,
  previewOverall,
  recordQualityTest,
  sccOver,
  type MilkBatch,
  type Chip,
  type CheckKey,
  type QualityTest,
  type QualityTestForm,
  type QualityTestOptions,
} from "@/lib/quality";
import { cn, fmt, todayISO } from "@/lib/utils";

const CHIP_STYLE: Record<NonNullable<Chip>, string> = {
  pass: "bg-[var(--sd-bg-soft)] text-[var(--sd-ink)] border-[var(--sd-line)]",
  warn: "border-[var(--sd-sev-warning,var(--sd-line))] text-[var(--sd-ink)]",
  fail: "border-[var(--sd-sev-critical)] text-[var(--sd-sev-critical)] font-semibold",
};
const CHIP_TEXT: Record<NonNullable<Chip>, string> = { pass: "Pass", warn: "Warn", fail: "Fail" };

/** Pass / Fail as a word and a mark, never colour alone. */
export function ResultChip({ label, chip }: { label: string; chip: Chip }) {
  if (!chip) return <span className="text-[11px] text-[var(--sd-quiet)]">{label} —</span>;
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]", CHIP_STYLE[chip])}
      data-chip={chip}
    >
      {label}: {CHIP_TEXT[chip]}
    </span>
  );
}

function Num({
  id, label, value, onChange, hint, signed,
}: { id: string; label: string; value: string; onChange: (v: string) => void; hint?: string; signed?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        inputMode="decimal"
        // text, not number: Fp and sensory take a minus sign and a comma decimal
        // on a phone keyboard, which a number input refuses.
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={signed ? "e.g. -0.548" : undefined}
      />
      {hint && <span className="text-[11px] text-[var(--sd-quiet)]">{hint}</span>}
    </div>
  );
}

/**
 * The buyer's quality sheet: record a batch result and read the history.
 * The same four server functions serve the phone's Milk quality screen.
 */
export function QualityBatch({ fileable = true, onSaved }: { fileable?: boolean; onSaved?: () => void }) {
  const [batches, setBatches] = useState<MilkBatch[]>([]);
  const [batchKey, setBatchKey] = useState("");
  const [opts, setOpts] = useState<QualityTestOptions | null>(null);
  const [form, setForm] = useState<QualityTestForm>(emptyForm(todayISO()));
  const [tests, setTests] = useState<QualityTest[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [onlyFails, setOnlyFails] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    const [o, l, b] = await Promise.all([
      getQualityTestOptions(),
      getQualityTests(onlyFails ? { overall_result: "Fail" } : {}),
      getMilkBatches(),
    ]);
    setLoading(false);
    if (isError(o)) return setFailure(o.error);
    if (isError(l)) return setFailure(l.error);
    if (isError(b)) return setFailure(b.error);
    setFailure(null);
    setOpts(o);
    setBatches(b.batches);
    // Pending first (the server orders them so); select the first awaiting result.
    setBatchKey((k) => (k && b.batches.some((x) => x.key === k) ? k : b.batches[0]?.key ?? ""));
    setTests(l.tests);
    setForm((f) => (f.buyer || !o.default_buyer ? f : { ...f, buyer: o.default_buyer }));
  }, [onlyFails]);

  useEffect(() => {
    void load();
  }, [load]);

  const set = (k: keyof QualityTestForm) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  const lim = opts?.limits ?? { aflatoxin_limit_ppt: 50, antibiotics_fail: true, resazurin_min_score: 4 };
  const checks = useMemo(() => previewChecks(form, lim), [form, lim]);
  const overall = previewOverall(checks);
  const batch = batches.find((x) => x.key === batchKey) ?? null;
  const ceiling = opts?.scc_ceiling ?? 0;
  const overCeiling = sccOver(form.bulk_scc, ceiling);

  async function pickFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    const r = await uploadFile(file);
    setUploading(false);
    if ("error" in r) return toast(r.error, "error");
    setForm((f) => ({ ...f, lab_slip: r.file_url }));
  }

  async function save() {
    const p = !batch ? "Pick the milked batch this result belongs to." : formProblem(form);
    setProblem(p);
    if (p || !batch) return;
    setSaving(true);
    const r = await recordQualityTest({ ...payloadFrom(form), ...batchFields(batch), client_ref: `desk_${Date.now()}` });
    setSaving(false);
    if (isError(r)) return toast(r.error, "error");
    toast(
      (r.overall_result === "Fail"
        ? `Filed ${r.name}. The milk failed: ${r.failed_tests}.`
        : `Filed ${r.name}. Overall: ${r.overall_result}.`) +
        (r.test.scc_over_ceiling ? " The cell count is above the farm's ceiling — worth a look at the herd." : ""),
    );
    setForm(emptyForm(todayISO(), form.buyer));
    void load();
    onSaved?.();
  }

  return (
    <>
      {failure && <Notice tone="error">{failure}</Notice>}
      {fileable && <Card aria-label="Record quality batch">
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Record quality batch</CardTitle>
            <CardDescription>
              Pick the milked batch, then fill in what the lab sent back. The bulk SCC, fat and
              protein also go onto the batch&apos;s milk recordings. Aflatoxin fails above{" "}
              {lim.aflatoxin_limit_ppt || "—"} ppt — change it in Settings.
            </CardDescription>
          </CardHeading>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-4 pt-0">
          <section aria-label="Step 1: pick the batch" className="flex flex-col gap-2">
            <Label>1. Which milking batch?</Label>
            {!batches.length ? (
              <p className="text-[13px] text-[var(--sd-muted)]">No milkings recorded in the last 14 days.</p>
            ) : (
              <ul className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                {batches.map((b) => (
                  <li key={b.key}>
                    <button
                      type="button"
                      aria-pressed={b.key === batchKey}
                      onClick={() => setBatchKey(b.key)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] border px-3 py-2 text-left transition-all",
                        b.key === batchKey ? "border-[var(--sd-ink)] bg-[var(--sd-bg-soft)]" : "border-[var(--sd-line)] hover:bg-[var(--sd-bg-soft)]",
                      )}
                    >
                      <FlaskConical className="h-4 w-4 shrink-0 text-[var(--sd-quiet)]" strokeWidth={1.75} />
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                          {b.date} · {b.shift}
                        </span>
                        <span className="truncate text-[11.5px] text-[var(--sd-muted)]">
                          {b.herds.join(", ")} · {fmt(b.total_kg)} kg
                        </span>
                      </span>
                      {b.pending ? (
                        <span className="shrink-0 rounded-full border border-[var(--sd-sev-critical)] px-2 py-0.5 text-[11px] text-[var(--sd-sev-critical)]">Awaiting result</span>
                      ) : b.tested ? (
                        <span className="shrink-0 text-[11px] text-[var(--sd-quiet)]">Tested</span>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <Label>2. What the lab sent back</Label>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qb-type">Sample type</Label>
              <Picker id="qb-type" label="Sample type" value={form.sample_type} onChange={set("sample_type")} options={opts?.sample_types ?? ["Bottle sample", "Tanker", "Can"]} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qb-buyer">Buyer / lab</Label>
              <Input id="qb-buyer" value={form.buyer} onChange={(e) => set("buyer")(e.target.value)} placeholder="Customer" />
            </div>
            <Num id="qb-qty" label="Quantity (L)" value={form.quantity_l} onChange={set("quantity_l")} />
            <Num id="qb-temp" label="Receiving temp (°C)" value={form.receiving_temp_c} onChange={set("receiving_temp_c")} />
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qb-scc">Bulk SCC (cells/ml × 1000)</Label>
              <Input
                id="qb-scc"
                inputMode="decimal"
                value={form.bulk_scc}
                onChange={(e) => set("bulk_scc")(e.target.value)}
                className={overCeiling ? "border-[var(--sd-sev-critical)]" : undefined}
              />
              {ceiling > 0 && <span className="text-[11px] text-[var(--sd-quiet)]">Ceiling {fmt(ceiling)}</span>}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Num id="qb-ph" label="pH" value={form.ph} onChange={set("ph")} />
            <Num id="qb-tta" label="TTA" value={form.tta} onChange={set("tta")} />
            <Num id="qb-snf" label="SNF %" value={form.snf_percent} onChange={set("snf_percent")} />
            <Num id="qb-fp" label="Freezing point (°C)" value={form.freezing_point} onChange={set("freezing_point")} signed hint="Below zero; a plus is read as minus." />
            <Num id="qb-sg" label="Specific gravity" value={form.specific_gravity} onChange={set("specific_gravity")} />
            <Num id="qb-protein" label="Protein %" value={form.protein_percent} onChange={set("protein_percent")} />
            <Num id="qb-fat" label="Butter fat %" value={form.butterfat_percent} onChange={set("butterfat_percent")} />
            <Num id="qb-afla" label="Aflatoxin M1 (ppt)" value={form.aflatoxin_ppt} onChange={set("aflatoxin_ppt")} />
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qb-rz">Resazurin score (0-6)</Label>
              <Picker id="qb-rz" label="Resazurin score" clearable value={form.resazurin_score} onChange={set("resazurin_score")} options={["0", "1", "2", "3", "4", "5", "6"]} placeholder="—" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qb-rzr">Resazurin result</Label>
              <Picker id="qb-rzr" label="Resazurin result" clearable value={form.resazurin_result} onChange={set("resazurin_result")} options={["Pass", "Fail"]} placeholder="From score" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qb-ab">Antibiotics</Label>
              <Picker id="qb-ab" label="Antibiotics" clearable value={form.antibiotics} onChange={set("antibiotics")} options={["Negative", "Positive"]} placeholder="—" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qb-hp">Hydrogen peroxide</Label>
              <Picker id="qb-hp" label="Hydrogen peroxide" clearable value={form.hydrogen_peroxide} onChange={set("hydrogen_peroxide")} options={["Nil", "Present"]} placeholder="—" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qb-fr">Frothing</Label>
              <Picker id="qb-fr" label="Frothing" clearable value={form.frothing} onChange={set("frothing")} options={["Pass", "Fail"]} placeholder="—" />
            </div>
            <Num id="qb-sens" label="Sensory score" value={form.sensory_score} onChange={set("sensory_score")} signed hint="Taste and smell, e.g. +1" />
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label htmlFor="qb-note">Sensory note</Label>
              <Input id="qb-note" value={form.sensory_note} onChange={(e) => set("sensory_note")(e.target.value)} placeholder="Taste / smell" />
            </div>
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label htmlFor="qb-remarks">Remarks</Label>
              <Input id="qb-remarks" value={form.remarks} onChange={(e) => set("remarks")(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label htmlFor="qb-slip">Lab slip photo</Label>
              <input id="qb-slip" type="file" accept="image/*" onChange={(e) => void pickFile(e.target.files?.[0])} className="text-[12px]" />
              {uploading && <span className="text-[11px] text-[var(--sd-quiet)]">Uploading…</span>}
              {form.lab_slip && !uploading && <span className="text-[11px] text-[var(--sd-muted)]">Attached.</span>}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2" aria-label="Result preview">
            {(Object.keys(CHECK_LABELS) as CheckKey[]).map((k) => (
              <ResultChip key={k} label={CHECK_LABELS[k]} chip={checks[k]} />
            ))}
            <span className={cn("ml-2 text-[13px] font-semibold", overall === "Fail" && "text-[var(--sd-sev-critical)]")}>
              Overall: {overall}
            </span>
          </div>

          {overCeiling && (
            <Notice tone="error">
              <span className="inline-flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                {fmt(Number(form.bulk_scc.replace(",", ".")))} is above the farm&apos;s ceiling of {fmt(ceiling)}. It will
                still be filed — the figure is the figure — and flagged in the results.
              </span>
            </Notice>
          )}
          {problem && <Notice tone="error">{problem}</Notice>}
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={save} disabled={saving || uploading || !opts?.can_write}>
              {saving ? "Filing…" : "Record batch"}
            </Button>
            {opts && !opts.can_write && (
              <span className="text-[12px] text-[var(--sd-muted)]">You may read these but not record them.</span>
            )}
          </div>
        </CardContent>
      </Card>}

      <Card aria-label="Quality batch history">
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Batch results</CardTitle>
            <CardDescription>One row per batch test, the last ninety days, newest first.</CardDescription>
          </CardHeading>
          <CardTools>
            <Button variant="outline" size="sm" onClick={() => setOnlyFails((v) => !v)} aria-pressed={onlyFails}>
              {onlyFails ? "Showing fails" : "Show fails only"}
            </Button>
            <RefreshButton onClick={load} loading={loading} label="the batch results" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="pt-0">
          {!tests.length ? (
            <p className="text-[13px] text-[var(--sd-muted)]">No batch results in this window.</p>
          ) : (
            <ScrollTable>
              <table className="w-full min-w-[900px] border-collapse text-[13px]">
                <thead className={STICKY_HEAD}>
                  <tr className="border-b border-[var(--sd-line)] text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3">Buyer</th>
                    <th className="py-2 pr-3 text-right">SCC</th>
                    <th className="py-2 pr-3 text-right">Fat / Protein / SNF %</th>
                    <th className="py-2 pr-3">Tests</th>
                    <th className="py-2 text-right">Overall</th>
                  </tr>
                </thead>
                <tbody>
                  {tests.map((t) => (
                    <tr key={t.name} className="border-b border-[var(--sd-line-soft)] align-top last:border-0">
                      <td className="py-2 pr-3 tabular-nums text-[var(--sd-ink)]">
                        {t.sample_date}
                        <div className="text-[11px] text-[var(--sd-quiet)]">{t.sample_type}{t.shift ? ` · ${t.shift}` : ""}</div>
                      </td>
                      <td className="py-2 pr-3 text-[var(--sd-muted)]">{t.buyer || "—"}</td>
                      <td
                        className={cn(
                          "py-2 pr-3 text-right tabular-nums",
                          t.scc_over_ceiling ? "font-semibold text-[var(--sd-sev-critical)]" : "text-[var(--sd-muted)]",
                        )}
                        data-over-ceiling={t.scc_over_ceiling ? "true" : undefined}
                      >
                        {t.bulk_scc ? fmt(t.bulk_scc) : "—"}
                        {t.scc_over_ceiling && <div className="text-[11px] font-normal">over ceiling</div>}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-[var(--sd-muted)]">
                        {[t.butterfat_percent, t.protein_percent, t.snf_percent].map((n) => (n == null ? "—" : n.toFixed(2))).join(" / ")}
                      </td>
                      <td className="py-2 pr-3">
                        <div className="flex flex-wrap gap-1">
                          {(Object.keys(CHECK_LABELS) as CheckKey[]).map((k) => (
                            <ResultChip key={k} label={CHECK_LABELS[k]} chip={t.checks[k]} />
                          ))}
                        </div>
                      </td>
                      <td className={cn("py-2 text-right font-semibold", t.overall_result === "Fail" ? "text-[var(--sd-sev-critical)]" : "text-[var(--sd-ink)]")}>
                        {t.overall_result}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollTable>
          )}
        </CardContent>
      </Card>
    </>
  );
}
