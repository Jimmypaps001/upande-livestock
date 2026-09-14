import { useCallback, useEffect, useMemo, useState } from "react";
import { Syringe } from "lucide-react";
import { DatePicker } from "@/components/DatePicker";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { isError } from "@/lib/frappe";
import { addCaseTreatment, getOpenCases, type OpenCasesView } from "@/lib/events";
import { cn, todayISO } from "@/lib/utils";

/**
 * A treatment, against the case it belongs to.
 *
 * NOT AGAINST AN ANIMAL. A course of treatment is a sequence — three days of
 * an antibiotic, then a check — and hanging each dose off the animal instead of
 * the case loses the thing a vet actually needs to see, which is the course.
 * So the picker offers open cases, not cows.
 *
 * The drug comes out of the store as the treatment is recorded, which is why
 * the quantity matters and why the withdrawal period is asked for here rather
 * than remembered: milk from a treated cow has to be discarded, and the number
 * of days is a property of the dose, not of the drug.
 */
export function Treatment() {
  const [data, setData] = useState<OpenCasesView | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [when, setWhen] = useState(todayISO());
  const [drug, setDrug] = useState("");
  const [drugText, setDrugText] = useState("");
  const [dosage, setDosage] = useState("");
  const [qty, setQty] = useState("1");
  const [route, setRoute] = useState("");
  const [withdrawal, setWithdrawal] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getOpenCases();
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

  const cases = data?.cases ?? [];
  const chosen = useMemo(() => cases.find((c) => c.value === picked) || null, [cases, picked]);
  const named = drug || drugText.trim();

  async function send() {
    if (!picked || !named) return;
    setBusy(true);
    const r = await addCaseTreatment({
      case: picked,
      treatment_date: when,
      treatments: [
        {
          drug_item: drug || undefined,
          drug_name_text: drug ? undefined : drugText.trim(),
          dosage: dosage.trim() || undefined,
          qty: Number(qty) || 1,
          route: route || undefined,
          withdrawal_period_days: withdrawal ? Number(withdrawal) : undefined,
          notes: notes.trim() || undefined,
        },
      ],
    });
    setBusy(false);
    if (isError(r)) {
      setNote(r.error);
      return;
    }
    setNote(`Treatment added to ${picked}.`);
    setDosage("");
    setNotes("");
    void load();
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Treatment">
        A dose, added to the case it belongs to. The drug leaves the store as it
        is recorded, and the withdrawal period goes with it.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}
      {note && <Notice tone="info">{note}</Notice>}

      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Open cases</CardTitle>
              <CardDescription>Still being treated.</CardDescription>
            </CardHeading>
            <CardTools>
              <RefreshButton onClick={load} loading={loading} label="the cases" />
            </CardTools>
          </CardHeaderRow>
          <CardContent className="pt-0">
            {!cases.length ? (
              <p className="text-[13px] text-[var(--sd-muted)]">
                No case is open. A treatment belongs to a case — open one on the Health
                Case screen first.
              </p>
            ) : (
              <ul className="flex max-h-[440px] flex-col gap-1 overflow-y-auto">
                {cases.map((c) => (
                  <li key={c.value}>
                    <button
                      type="button"
                      onClick={() => setPicked(c.value)}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
                        c.value === picked ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate text-[13px] text-[var(--sd-ink)]">
                        {c.label}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>{chosen ? chosen.label : "Nothing selected"}</CardTitle>
              <CardDescription>
                {chosen ? `Case ${chosen.value}` : "Pick a case on the left."}
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-4 pt-0">
            {!chosen ? (
              <p className="text-[13px] text-[var(--sd-muted)]">
                A course of treatment is a sequence, and it is kept as one.
              </p>
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="t-when">Given on</Label>
                    <DatePicker id="t-when" value={when} max={todayISO()} onChange={setWhen} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="t-drug">Drug from the store</Label>
                    <select
                      id="t-drug"
                      value={drug}
                      onChange={(e) => setDrug(e.target.value)}
                      className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                    >
                      <option value="">—</option>
                      {(data?.drug_items ?? []).map((i) => (
                        <option key={i.value} value={i.value}>
                          {i.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  {!drug && (
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="t-drugtext">…or name it</Label>
                      <Input
                        id="t-drugtext"
                        value={drugText}
                        onChange={(e) => setDrugText(e.target.value)}
                        placeholder="Something the vet brought"
                      />
                      <span className="text-[11px] text-[var(--sd-quiet)]">
                        Nothing leaves the store for a drug it does not hold.
                      </span>
                    </div>
                  )}
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="t-dosage">Dose</Label>
                    <Input id="t-dosage" value={dosage} onChange={(e) => setDosage(e.target.value)}
                           placeholder="20 ml" />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="t-qty">Units taken</Label>
                    <Input id="t-qty" type="number" min={0} step="any" value={qty}
                           onChange={(e) => setQty(e.target.value)} />
                  </div>
                  {!!data?.routes?.length && (
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="t-route">Route</Label>
                      <select
                        id="t-route"
                        value={route}
                        onChange={(e) => setRoute(e.target.value)}
                        className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                      >
                        <option value="">—</option>
                        {data.routes.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="t-wd">Withdrawal (days)</Label>
                    <Input id="t-wd" type="number" min={0} value={withdrawal}
                           onChange={(e) => setWithdrawal(e.target.value)} />
                    <span className="text-[11px] text-[var(--sd-quiet)]">
                      How long her milk must be discarded.
                    </span>
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="t-notes">Notes</Label>
                  <Textarea id="t-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Button onClick={send} disabled={busy || !named}>
                    <Syringe className="mr-2 h-4 w-4" strokeWidth={1.75} />
                    {busy ? "Recording…" : "Add the treatment"}
                  </Button>
                  {!named && (
                    <span className="text-[11.5px] text-[var(--sd-muted)]">
                      Say which drug was given.
                    </span>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}
