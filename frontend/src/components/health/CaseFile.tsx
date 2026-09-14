import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, FileText, Stethoscope } from "lucide-react";
import { CaseTimeline } from "@/components/health/CaseTimeline";
import { DatePicker } from "@/components/DatePicker";
import { Notice } from "@/components/feeding/Notice";
import { RowsSkeleton } from "@/components/Loading";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { Textarea } from "@/components/ui/textarea";
import { isError } from "@/lib/frappe";
import {
  CLOSED_STATUSES, closeCase, getCaseFile, type CaseFile as Case,
} from "@/lib/health";
import { cn, fmt, todayISO } from "@/lib/utils";

/**
 * One file, read.
 *
 * A CASE IS NOT A FORM. It is the record of something that happened over days,
 * and the only thing that can be added to it is a treatment — a new fact with
 * its own date, recorded where treatments are recorded. So the front of the
 * file is read-only here: the animal, the day, the complaint it was opened on,
 * the diagnosis somebody thought at the time.
 *
 * The one thing this screen writes is the ending, because a file nobody can
 * close is a file that stays open forever — which is how this farm ended up
 * with a cow carrying three of them at once.
 */
export function CaseFile({
  name,
  onBack,
  onChanged,
}: {
  name: string;
  onBack?: () => void;
  onChanged?: () => void;
}) {
  const [file, setFile] = useState<Case | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [ending, setEnding] = useState("");
  const [closedOn, setClosedOn] = useState(todayISO());
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function load() {
    const r = await getCaseFile(name);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setFile(r);
  }

  useEffect(() => {
    setFile(null);
    void load();
  }, [name]);

  async function shut() {
    if (!ending) return;
    setBusy(true);
    const r = await closeCase({
      case: name,
      case_status: ending,
      closed_date: closedOn,
      outcome_notes: notes.trim() || undefined,
    });
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast(
      `${name} is closed — ${r.case_status.toLowerCase()} after ${r.duration_days ?? 0} days.`,
    );
    setEnding("");
    setNotes("");
    void load();
    onChanged?.();
  }

  if (failure) return <Notice tone="error">{failure}</Notice>;
  if (!file) return <RowsSkeleton rows={6} />;

  const c = file.case;

  return (
    <div className="flex min-w-0 flex-col gap-5">
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 self-start text-[12.5px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)]"
        >
          <ArrowLeft className="h-4 w-4" />
          All files
        </button>
      )}

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>
              {c.animal_name}
              <span className="ml-2 text-[12px] font-normal text-[var(--sd-quiet)]">
                {c.name}
              </span>
            </CardTitle>
            <CardDescription>
              Opened {c.opened_date}
              {c.opened_by ? ` by ${c.opened_by}` : ""} · {c.herd || "no herd"} ·{" "}
              {c.open ? `open ${c.days_open} days` : `closed ${c.closed_date}`}
            </CardDescription>
          </CardHeading>
          <span
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 rounded-[var(--sd-radius-pill)] px-3 py-1.5 text-[12px]",
              c.open
                ? "bg-[var(--sd-bg-soft)] text-[var(--sd-ink)]"
                : "bg-[var(--sd-bg-soft)] text-[var(--sd-muted)]",
            )}
          >
            {c.open ? (
              <Stethoscope className="h-3.5 w-3.5" strokeWidth={1.75} />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />
            )}
            {c.case_status}
          </span>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-4 pt-0">
          {c.concern && <Notice tone="info">{c.concern.says}</Notice>}

          <div className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3.5 shadow-[var(--sd-shadow-inset)]">
            <p className="text-[13px] leading-relaxed text-[var(--sd-ink)]">
              {c.presenting_symptoms || "No complaint was written on the file."}
            </p>
            <p className="mt-2 text-[11.5px] text-[var(--sd-quiet)]">
              {[
                c.provisional_diagnosis ? `thought to be ${c.provisional_diagnosis}` : null,
                c.confirmed_diagnosis ? `confirmed ${c.confirmed_diagnosis}` : null,
                c.severity ? c.severity.toLowerCase() : null,
                c.body_systems || null,
                c.vet_called ? `vet ${c.vet_name || "called"}` : "no vet called",
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>

          <FactRow file={file} />
        </CardContent>
      </Card>

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>The course</CardTitle>
            <CardDescription>{file.verdict.says}</CardDescription>
          </CardHeading>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-4 pt-0">
          <CaseTimeline entries={file.entries} />

          {!!file.entries.length && (
            <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] shadow-[var(--sd-shadow-inset)]">
              <table className="w-full min-w-[520px] border-collapse text-[12.5px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-[0.06em] text-[var(--sd-quiet)]">
                    <th className="px-3.5 py-2 font-medium">Day</th>
                    <th className="px-3 py-2 font-medium">Given</th>
                    <th className="px-3 py-2 text-right font-medium">Qty</th>
                    <th className="px-3 py-2 font-medium">How</th>
                    <th className="px-3.5 py-2 font-medium">Response</th>
                  </tr>
                </thead>
                <tbody>
                  {file.entries.map((e) => (
                    <tr key={e.name} className="border-t border-[var(--sd-line)]">
                      <td className="px-3.5 py-1.5 tabular-nums">
                        <span className="text-[var(--sd-ink)]">{e.day ?? "—"}</span>
                        <span className="ml-2 text-[11px] text-[var(--sd-quiet)]">{e.on}</span>
                      </td>
                      <td className="px-3 py-1.5">
                        <span className="text-[var(--sd-ink)]">{e.drug || "—"}</span>
                        {e.dosage && (
                          <span className="ml-2 text-[11px] text-[var(--sd-quiet)]">{e.dosage}</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-[var(--sd-muted)]">
                        {fmt(e.qty)}
                      </td>
                      <td className="px-3 py-1.5 text-[var(--sd-muted)]">
                        {e.route || "—"}
                        {e.withdrawal_days ? (
                          <span className="ml-2 text-[11px] text-[var(--sd-sev-moderate)]">
                            {e.withdrawal_days} d withdrawal
                          </span>
                        ) : null}
                      </td>
                      <td className="px-3.5 py-1.5">
                        {e.response ? (
                          <span className="text-[var(--sd-ink)]">{e.response}</span>
                        ) : (
                          <span className="italic text-[var(--sd-quiet)]">not assessed</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!!file.drugs.length && (
            <p className="text-[12px] text-[var(--sd-muted)]">
              Out of the store for her:{" "}
              {file.drugs
                .map((d) => `${fmt(d.qty)} ${d.uom || ""} ${d.drug} (${d.times}×)`.trim())
                .join(", ")}
              .
            </p>
          )}
        </CardContent>
      </Card>

      {c.open && (
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Close the file</CardTitle>
              <CardDescription>
                How it ended, and on what day. A file shut with no ending is the
                same as one left open, except it stops being counted.
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-4 pt-0">
            <div className="flex flex-wrap items-end gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cf-ending">How it ended</Label>
                <Picker
                  id="cf-ending"
                  value={ending}
                  onChange={setEnding}
                  options={[...CLOSED_STATUSES]}
                  label="How it ended"
                  placeholder="Choose…"
                  className="w-[180px]"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cf-when">On</Label>
                <DatePicker id="cf-when" value={closedOn} max={todayISO()} onChange={setClosedOn} />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cf-notes">Notes</Label>
              <Textarea id="cf-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={shut} disabled={!ending || busy}>
                <FileText className="mr-2 h-4 w-4" strokeWidth={1.75} />
                {busy ? "Closing…" : "Close the file"}
              </Button>
              {(ending === "Died" || ending === "Culled") && (
                <span className="text-[11.5px] text-[var(--sd-muted)]">
                  This records how the illness ended. Taking her off the farm is a
                  disposal, with a vet and a manager behind it.
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {!!file.others.length && (
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Her other files</CardTitle>
              <CardDescription>
                A cow on her fourth file for the same quarter in a year is a
                different conversation from one on her first.
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="pt-0">
            <ul className="flex flex-col gap-1">
              {file.others.map((o) => (
                <li
                  key={o.name}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 px-1 py-1.5 text-[12.5px]"
                >
                  <span className="text-[var(--sd-ink)]">
                    {o.opened_date}
                    <span className="ml-2 text-[var(--sd-muted)]">
                      {o.provisional_diagnosis || "no diagnosis recorded"}
                    </span>
                  </span>
                  <span className="tabular-nums text-[var(--sd-quiet)]">
                    {o.case_status}
                    {o.closed_date ? ` · ${o.closed_date}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function FactRow({ file }: { file: Case }) {
  const c = file.case;
  const facts: { label: string; value: string }[] = [
    { label: "Treatments", value: String(file.entries.length) },
    {
      label: "Drugs issued",
      value: file.drugs.length ? `${file.drugs.length} kind${file.drugs.length === 1 ? "" : "s"}` : "none",
    },
    {
      label: "Milk withheld to",
      value: c.milk_safe_date || "—",
    },
    {
      label: "Milk lost",
      value: c.production_loss_kg ? `${fmt(c.production_loss_kg)} kg` : "not recorded",
    },
  ];
  return (
    <div className="flex flex-wrap gap-x-8 gap-y-2">
      {facts.map((f) => (
        <span key={f.label} className="flex flex-col">
          <span className="text-[10.5px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
            {f.label}
          </span>
          <span className="text-[13px] text-[var(--sd-ink)]">{f.value}</span>
        </span>
      ))}
    </div>
  );
}
