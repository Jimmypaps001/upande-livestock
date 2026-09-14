import { useCallback, useEffect, useMemo, useState } from "react";
import { FileText, FolderOpen, Plus, Syringe, X } from "lucide-react";
import { AnimalSearch } from "@/components/animals/AnimalSearch";
import { DatePicker } from "@/components/DatePicker";
import { Notice } from "@/components/feeding/Notice";
import { OperatorField } from "@/components/events/OperatorField";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { Textarea } from "@/components/ui/textarea";
import { isError } from "@/lib/frappe";
import type { AnimalSummary } from "@/lib/animals";
import { getHealthOptions, getOpenCases, type HealthOptions, type OpenCasesView } from "@/lib/events";
import { getAnimalCase, treatAnimal, type AnimalCaseStanding } from "@/lib/health";
import { useOperator } from "@/lib/operator";
import { useSaveShortcut } from "@/lib/use-save-shortcut";
import { cn, fmt, todayISO } from "@/lib/utils";

interface Dose {
  key: number;
  drug: string;
  qty: string;
  dosage: string;
  route: string;
  withdrawal: string;
  response: string;
  notes: string;
}

let nextKey = 1;

const RESPONSES = ["Improving", "No Change", "Worsening", "Resolved", "Not Yet Assessed"];

const blank = (): Dose => ({
  key: nextKey++,
  drug: "",
  qty: "1",
  dosage: "",
  route: "",
  withdrawal: "",
  response: "",
  notes: "",
});

/**
 * Treating an animal, which is also how a file gets opened.
 *
 * THE SCREEN USED TO ASK FOR A CASE. You picked one off a list of open cases
 * and added a dose to it — which works only if somebody has already opened the
 * right file, on another screen, for the right cow. In practice the drug went
 * out of the store against whatever case was nearest, or against none.
 *
 * So it asks for the COW, and then tells you what she already has: a file open
 * eleven days with four treatments in it, or nothing. Writing into the file she
 * has is the default, because a second file for an illness already being
 * treated is exactly what scatters one bout of mastitis across three records.
 * Starting a fresh one is a deliberate answer with a complaint attached — the
 * same as coming back to a hospital months later and being given a new file.
 *
 * THE RESPONSE IS ASKED FOR HERE. It is the column that makes a file readable
 * afterwards — five doses with no responses cannot say whether she got better —
 * and the only moment anybody knows the answer is standing next to her.
 */
export function Treatment() {
  const [options, setOptions] = useState<HealthOptions | null>(null);
  const [store, setStore] = useState<OpenCasesView | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const toast = useToast();
  const who = useOperator(options?.employee);

  const [animal, setAnimal] = useState<string | null>(null);
  const [standing, setStanding] = useState<AnimalCaseStanding | null>(null);
  const [asking, setAsking] = useState(false);
  const [fresh, setFresh] = useState(false);
  const [complaint, setComplaint] = useState("");
  const [suspected, setSuspected] = useState("");
  const [severity, setSeverity] = useState("");
  const [when, setWhen] = useState(todayISO());
  const [doses, setDoses] = useState<Dose[]>([blank()]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [o, s] = await Promise.all([getHealthOptions(), getOpenCases()]);
    setLoading(false);
    if (isError(o)) {
      setFailure(o.error);
      return;
    }
    setFailure(null);
    setOptions(o);
    if (!isError(s)) setStore(s);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Her standing is asked for the moment she is picked, because the answer
  // changes what this screen is: adding to a course, or starting one.
  useEffect(() => {
    if (!animal) {
      setStanding(null);
      return;
    }
    let live = true;
    setAsking(true);
    void getAnimalCase(animal).then((r) => {
      if (!live) return;
      setAsking(false);
      setStanding(isError(r) ? null : r);
      setFresh(isError(r) ? true : !r.open_case);
    });
    return () => {
      live = false;
    };
  }, [animal]);

  // The search wants a herd summary and the options endpoint answers a picker
  // list; the fields it cannot know — her breed, her birthday — are null rather
  // than invented, and the search does not read them.
  const roster: AnimalSummary[] = useMemo(
    () =>
      (options?.animals ?? []).map((a) => ({
        id: a.name,
        name: a.label,
        sex: "Female" as const,
        herd: a.herd_label || a.herd || "no herd",
        breed: null,
        bornOn: null,
        status: "Active",
        stage: "open" as const,
        photo: null,
      })),
    [options],
  );

  const usable = doses.filter((d) => d.drug && Number(d.qty) > 0);
  const needComplaint = fresh && !complaint.trim();
  const ready = !!animal && usable.length > 0 && !needComplaint && !who.needed && !asking;

  useSaveShortcut(() => void send(), ready && !busy);

  async function send() {
    if (!ready || !animal) return;
    setBusy(true);
    const r = await treatAnimal({
      animal,
      case: !fresh && standing?.open_case ? standing.open_case.name : undefined,
      open_new: fresh || undefined,
      presenting_symptoms: fresh ? complaint.trim() : undefined,
      provisional_diagnosis: fresh ? suspected || undefined : undefined,
      severity: fresh ? severity || undefined : undefined,
      operator: who.value,
      opened_by: who.value,
      treatment_date: when,
      treatments: usable.map((d) => ({
        drug_item: d.drug,
        qty: Number(d.qty),
        dosage: d.dosage || undefined,
        route: d.route || undefined,
        withdrawal_period_days: d.withdrawal ? Number(d.withdrawal) : undefined,
        response_observed: d.response || undefined,
        administered_by: who.value,
        notes: d.notes || undefined,
      })),
    });
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast(
      r.opened
        ? `A new file is open for ${r.animal} — ${r.case} — with ${r.added} treatment${r.added === 1 ? "" : "s"} in it.`
        : `${r.added} treatment${r.added === 1 ? "" : "s"} added to ${r.case}. ${r.treatments} in the file now.`,
    );
    setDoses([blank()]);
    setComplaint("");
    setSuspected("");
    setSeverity("");
    void getAnimalCase(animal).then((again) => {
      if (!isError(again)) {
        setStanding(again);
        setFresh(!again.open_case);
      }
    });
  }

  const openCase = standing?.open_case ?? null;

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Treatment">
        Treating an animal. It goes into the file she already has, or opens a new
        one — the way a hospital gives you a new file when you come back months
        later with something else.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        <Card className="lg:sticky lg:top-6 lg:self-start">
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Which animal</CardTitle>
              <CardDescription>Her file is looked up as you pick her.</CardDescription>
            </CardHeading>
            <CardTools>
              <RefreshButton onClick={load} loading={loading} label="the list" />
            </CardTools>
          </CardHeaderRow>
          <CardContent className="pt-0">
            <AnimalSearch
              animals={roster}
              selectedId={animal}
              onSelect={(a) => setAnimal(a.id)}
            />
          </CardContent>
        </Card>

        <div className="flex min-w-0 flex-col gap-5">
          <Card>
            <CardHeaderRow>
              <CardHeading>
                <CardTitle>{animal ? `Her file` : "Pick an animal"}</CardTitle>
                <CardDescription>
                  {!animal
                    ? "Nothing is written down until you say what she was given."
                    : asking
                      ? "Looking her up…"
                      : openCase
                        ? `Open since ${openCase.opened_date} — ${openCase.days_open} days, ${openCase.treatments} treatment${openCase.treatments === 1 ? "" : "s"}.`
                        : "She has no open file."}
                </CardDescription>
              </CardHeading>
            </CardHeaderRow>
            <CardContent className="flex flex-col gap-4 pt-0">
              {animal && !asking && (
                <>
                  {openCase && (
                    <div className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3.5 shadow-[var(--sd-shadow-inset)]">
                      <p className="flex items-start gap-2 text-[13px] leading-relaxed text-[var(--sd-ink)]">
                        <FolderOpen
                          className="mt-0.5 h-4 w-4 shrink-0 text-[var(--sd-quiet)]"
                          strokeWidth={1.75}
                        />
                        <span>
                          {openCase.presenting_symptoms || "No complaint on the file."}
                          {openCase.provisional_diagnosis
                            ? ` — thought to be ${openCase.provisional_diagnosis}.`
                            : ""}
                        </span>
                      </p>
                    </div>
                  )}

                  {!!standing?.closed_count && (
                    <p className="text-[11.5px] text-[var(--sd-quiet)]">
                      {standing.closed_count} closed file
                      {standing.closed_count === 1 ? "" : "s"} before this
                      {standing.history[0]?.opened_date
                        ? `, the last opened ${standing.history[0].opened_date}`
                        : ""}
                      .
                    </p>
                  )}

                  {openCase ? (
                    <div className="flex flex-wrap gap-2">
                      <Choice
                        on={!fresh}
                        onClick={() => setFresh(false)}
                        title="Add to her open file"
                        blurb="The same illness, still being treated."
                      />
                      <Choice
                        on={fresh}
                        onClick={() => setFresh(true)}
                        title="Open a new file"
                        blurb="Something else. Her open one stays open."
                      />
                    </div>
                  ) : (
                    <Notice tone="info">
                      She has no open file, so this treatment opens one. Say what is
                      wrong with her.
                    </Notice>
                  )}

                  {fresh && (
                    <div className="flex flex-col gap-4">
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="tx-complaint">What is wrong</Label>
                        <Input
                          id="tx-complaint"
                          value={complaint}
                          onChange={(e) => setComplaint(e.target.value)}
                          placeholder="Swollen left hind quarter, hard"
                        />
                      </div>
                      <div className="flex flex-wrap items-end gap-4">
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor="tx-suspect">Thought to be</Label>
                          <Picker
                            id="tx-suspect"
                            value={suspected}
                            onChange={setSuspected}
                            options={options?.diseases ?? []}
                            label="Thought to be"
                            placeholder="Not said"
                            className="w-[200px]"
                          />
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor="tx-severity">How bad</Label>
                          <Picker
                            id="tx-severity"
                            value={severity}
                            onChange={setSeverity}
                            options={options?.severities ?? []}
                            label="How bad"
                            placeholder="Not said"
                            className="w-[150px]"
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeaderRow>
              <CardHeading>
                <CardTitle>What she was given</CardTitle>
                <CardDescription>
                  Out of the drug store as it is recorded. The response is what
                  makes the file readable afterwards.
                </CardDescription>
              </CardHeading>
            </CardHeaderRow>
            <CardContent className="flex flex-col gap-4 pt-0">
              <div className="flex flex-wrap items-end gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="tx-when">Given on</Label>
                  <DatePicker id="tx-when" value={when} max={todayISO()} onChange={setWhen} />
                </div>
                {who.mustAsk && (
                  <OperatorField operator={who.operator} onChange={who.setOperator} />
                )}
              </div>

              {doses.map((d, i) => (
                <div
                  key={d.key}
                  className="flex flex-col gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]"
                >
                  <div className="flex flex-wrap items-end gap-3">
                    <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
                      <Label htmlFor={`tx-drug-${d.key}`}>Drug</Label>
                      <Picker
                        id={`tx-drug-${d.key}`}
                        value={d.drug}
                        onChange={(v) => set(i, { drug: v })}
                        options={(store?.drug_items ?? []).map((x) => ({
                          value: x.value,
                          label: x.label,
                        }))}
                        label="Drug"
                        placeholder="From the store…"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor={`tx-qty-${d.key}`}>Qty</Label>
                      <Input
                        id={`tx-qty-${d.key}`}
                        type="number"
                        min={0}
                        step="any"
                        value={d.qty}
                        onChange={(e) => set(i, { qty: e.target.value })}
                        className="w-24 text-right tabular-nums"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor={`tx-dosage-${d.key}`}>Dose</Label>
                      <Input
                        id={`tx-dosage-${d.key}`}
                        value={d.dosage}
                        onChange={(e) => set(i, { dosage: e.target.value })}
                        placeholder="20 ml"
                        className="w-28"
                      />
                    </div>
                    {doses.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setDoses((s) => s.filter((_, j) => j !== i))}
                        aria-label="Take this drug off"
                        className="mb-2 text-[var(--sd-quiet)] transition-colors hover:text-[var(--sd-sev-critical)]"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                  <div className="flex flex-wrap items-end gap-3">
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor={`tx-route-${d.key}`}>How</Label>
                      <Picker
                        id={`tx-route-${d.key}`}
                        value={d.route}
                        onChange={(v) => set(i, { route: v })}
                        options={(options?.routes ?? []).filter(Boolean)}
                        label="How"
                        placeholder="Route"
                        className="w-[180px]"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor={`tx-wd-${d.key}`}>Withdrawal (days)</Label>
                      <Input
                        id={`tx-wd-${d.key}`}
                        type="number"
                        min={0}
                        value={d.withdrawal}
                        onChange={(e) => set(i, { withdrawal: e.target.value })}
                        className="w-28 text-right tabular-nums"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor={`tx-resp-${d.key}`}>How she is</Label>
                      <Picker
                        id={`tx-resp-${d.key}`}
                        value={d.response}
                        onChange={(v) => set(i, { response: v })}
                        options={RESPONSES}
                        label="How she is"
                        placeholder="Not assessed"
                        className="w-[170px]"
                      />
                    </div>
                  </div>
                </div>
              ))}

              <button
                type="button"
                onClick={() => setDoses((s) => [...s, blank()])}
                className="inline-flex w-fit items-center gap-1.5 text-[12.5px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)]"
              >
                <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
                Another drug
              </button>

              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={send} disabled={!ready || busy}>
                  <Syringe className="mr-2 h-4 w-4" strokeWidth={1.75} />
                  {busy
                    ? "Recording…"
                    : fresh
                      ? "Open a file and record it"
                      : "Add it to her file"}
                </Button>
                {!animal && (
                  <span className="text-[11.5px] text-[var(--sd-muted)]">
                    Pick the animal first.
                  </span>
                )}
                {animal && needComplaint && (
                  <span className="text-[11.5px] text-[var(--sd-muted)]">
                    A new file needs a complaint on the front of it.
                  </span>
                )}
                {animal && !needComplaint && !usable.length && (
                  <span className="text-[11.5px] text-[var(--sd-muted)]">
                    Pick a drug and a quantity.
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {!!standing?.history.length && (
            <Card>
              <CardHeaderRow>
                <CardHeading>
                  <CardTitle>Her closed files</CardTitle>
                  <CardDescription>
                    A cow on her fourth file for the same thing in a year is a
                    different conversation from one on her first.
                  </CardDescription>
                </CardHeading>
              </CardHeaderRow>
              <CardContent className="pt-0">
                <ul className="flex flex-col gap-1">
                  {standing.history.map((h) => (
                    <li
                      key={h.name}
                      className="flex flex-wrap items-baseline justify-between gap-x-4 px-1 py-1.5 text-[12.5px]"
                    >
                      <span className="text-[var(--sd-ink)]">
                        {h.opened_date}
                        <span className="ml-2 text-[var(--sd-muted)]">
                          {h.provisional_diagnosis || h.presenting_symptoms || "not recorded"}
                        </span>
                      </span>
                      <span className="tabular-nums text-[var(--sd-quiet)]">
                        {h.case_status}
                        {h.duration_days != null ? ` · ${fmt(h.duration_days)} days` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </Page>
  );

  function set(i: number, patch: Partial<Dose>) {
    setDoses((s) => s.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  }
}

function Choice({
  on,
  onClick,
  title,
  blurb,
}: {
  on: boolean;
  onClick: () => void;
  title: string;
  blurb: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "min-w-[200px] flex-1 rounded-[var(--sd-radius-lg)] px-3.5 py-3 text-left transition-all",
        on
          ? "bg-[var(--sd-bg-soft)] shadow-[var(--sd-shadow-1)]"
          : "hover:bg-[var(--sd-bg-soft)]",
      )}
    >
      <span className="flex items-center gap-1.5 text-[13px] font-medium text-[var(--sd-ink)]">
        <FileText className="h-3.5 w-3.5 text-[var(--sd-quiet)]" strokeWidth={1.75} />
        {title}
      </span>
      <span className="mt-0.5 block text-[11.5px] leading-snug text-[var(--sd-muted)]">
        {blurb}
      </span>
    </button>
  );
}
