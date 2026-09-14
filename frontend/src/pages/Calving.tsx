import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Baby, Plus, X } from "lucide-react";
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
import {
  getCalvingDestinations,
  getMovementOptions,
  recordBirth,
  type AnimalChoice,
  type CalvingDestinations,
  type MovementOptions,
} from "@/lib/events";
import { OperatorField } from "@/components/events/OperatorField";
import { useOperator } from "@/lib/operator";
import { cn, todayISO } from "@/lib/utils";

interface CalfRow {
  key: number;
  sex: "Female" | "Male";
  burn_name: string;
  birth_weight: string;
  is_stillborn: boolean;
}

let nextKey = 1;
const blankCalf = (): CalfRow => ({
  key: nextKey++,
  sex: "Female",
  burn_name: "",
  birth_weight: "",
  is_stillborn: false,
});

/**
 * A calving: the cow, the calves, and where all of them end up.
 *
 * THREE ANIMALS CHANGE HERD AT A CALVING and until recently two of them did —
 * the calves were routed by sex and the cow stayed in the dry herd she calved
 * in, because nothing moved her. So the destinations are shown BEFORE anything
 * is written, while the person at the pen can still say it is wrong.
 *
 * NO TAG IS ASKED FOR. A calf's number is the farm's next register entry and
 * the system hands it out — A057/26 for a heifer, B014/26 for a bull. Letting
 * somebody type one here is how two animals end up sharing a number.
 */
export function Calving() {
  const [options, setOptions] = useState<MovementOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [dam, setDam] = useState<string | null>(null);
  const [when, setWhen] = useState(todayISO());
  const [remarks, setRemarks] = useState("");
  const [calves, setCalves] = useState<CalfRow[]>([blankCalf()]);
  const [where, setWhere] = useState<CalvingDestinations | null>(null);
  const [busy, setBusy] = useState(false);
  const [term, setTerm] = useState("");
  const who = useOperator(options?.employee);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getMovementOptions();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setOptions(r);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Asked the moment a cow is picked, because it is a question and not the
  // first half of the answer — nothing is written by asking.
  useEffect(() => {
    let live = true;
    if (!dam) {
      setWhere(null);
      return;
    }
    void getCalvingDestinations(dam).then((r) => {
      if (live) setWhere(isError(r) ? null : r);
    });
    return () => {
      live = false;
    };
  }, [dam]);

  const animals = options?.animals ?? [];
  const chosen = animals.find((a) => a.name === dam) || null;
  const results = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return animals;
    return animals.filter((a) =>
      [a.name, a.label, a.herd_label || ""].some((f) => f.toLowerCase().includes(q)),
    );
  }, [animals, term]);

  async function send() {
    if (!dam) return;
    setBusy(true);
    const r = await recordBirth({
      dam,
      event_date: when,
      remarks: remarks.trim() || undefined,
      operator: who.value,
      outcome: calves.every((c) => c.is_stillborn) ? "Still Birth" : "Live Birth",
      calves: calves.map((c) => ({
        sex: c.sex,
        burn_name: c.burn_name.trim() || undefined,
        birth_weight: c.birth_weight ? Number(c.birth_weight) : undefined,
        is_stillborn: c.is_stillborn,
      })),
    });
    setBusy(false);
    if (isError(r)) {
      setNote(r.error);
      return;
    }
    const born = (r.calves || []).map((c) => c.animal).filter(Boolean);
    setNote(
      born.length
        ? `${dam} calved — ${born.join(", ")} ${born.length === 1 ? "is" : "are"} on the farm.`
        : `${dam} calved — ${r.name}.`,
    );
    setDam(null);
    setCalves([blankCalf()]);
    setRemarks("");
    void load();
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Breeding" title="Calving">
        The cow, the calves, and where each of them stands afterwards. Numbers
        come from the farm's register — nobody types one.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}
      {note && <Notice tone="info">{note}</Notice>}

      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Which cow calved</CardTitle>
              <CardDescription>Any animal on the farm.</CardDescription>
            </CardHeading>
            <CardTools>
              <RefreshButton onClick={load} loading={loading} label="the list" />
            </CardTools>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-3 pt-0">
            <Input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Number, name or herd…"
              aria-label="Find the cow that calved"
              className="h-10 rounded-[var(--sd-radius-pill)] border-[var(--sd-line)] bg-[var(--sd-bg-soft)] text-[13px]"
            />
            <ul className="flex max-h-[420px] flex-col gap-1 overflow-y-auto">
              {results.map((a: AnimalChoice) => (
                <li key={a.name}>
                  <button
                    type="button"
                    onClick={() => setDam(a.name)}
                    className={cn(
                      "flex w-full flex-col rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
                      a.name === dam ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
                    )}
                  >
                    <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                      {a.label}
                    </span>
                    <span className="truncate text-[11.5px] text-[var(--sd-muted)]">
                      {a.herd_label || a.herd || "no herd"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <div className="flex min-w-0 flex-col gap-5">
          {where && chosen && (
            <Card>
              <CardHeaderRow>
                <CardHeading>
                  <CardTitle>Where everyone ends up</CardTitle>
                  <CardDescription>
                    Shown before anything is written, while it can still be called wrong.
                  </CardDescription>
                </CardHeading>
              </CardHeaderRow>
              <CardContent className="flex flex-col gap-2 pt-0">
                <Destination label={chosen.label} from={where.dam.from_herd} to={where.dam.to_herd}
                             moving={where.dam.will_move} reason={where.dam.reason} />
                <Destination label="A heifer calf" to={where.female_calf.to_herd} moving
                             reason={where.female_calf.reason} />
                <Destination label="A bull calf" to={where.male_calf.to_herd} moving
                             reason={where.male_calf.reason} />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeaderRow>
              <CardHeading>
                <CardTitle>{chosen ? `${chosen.label} calved` : "Nothing selected"}</CardTitle>
                <CardDescription>
                  {chosen ? "One row per calf, twins included." : "Pick a cow on the left."}
                </CardDescription>
              </CardHeading>
            </CardHeaderRow>
            <CardContent className="flex flex-col gap-4 pt-0">
              {!chosen ? (
                <p className="text-[13px] text-[var(--sd-muted)]">
                  A calving creates animals, so it asks for each one.
                </p>
              ) : (
                <>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="c-when">Calved on</Label>
                      <DatePicker id="c-when" value={when} max={todayISO()} onChange={setWhen} />
                    </div>
                  </div>

                  <div className="flex flex-col gap-2">
                    <Label>The calves</Label>
                    {calves.map((c, i) => (
                      <div
                        key={c.key}
                        className="flex flex-wrap items-end gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]"
                      >
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`c-sex-${c.key}`}>Sex</Label>
                          <select
                            id={`c-sex-${c.key}`}
                            value={c.sex}
                            onChange={(e) =>
                              setCalves((s) =>
                                s.map((x, j) =>
                                  j === i ? { ...x, sex: e.target.value as "Female" | "Male" } : x,
                                ),
                              )
                            }
                            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                          >
                            <option>Female</option>
                            <option>Male</option>
                          </select>
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`c-name-${c.key}`}>Name</Label>
                          <Input
                            id={`c-name-${c.key}`}
                            value={c.burn_name}
                            onChange={(e) =>
                              setCalves((s) =>
                                s.map((x, j) => (j === i ? { ...x, burn_name: e.target.value } : x)),
                              )
                            }
                            className="w-40"
                          />
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`c-wt-${c.key}`}>Birth weight (kg)</Label>
                          <Input
                            id={`c-wt-${c.key}`}
                            type="number"
                            min={0}
                            step="0.1"
                            value={c.birth_weight}
                            onChange={(e) =>
                              setCalves((s) =>
                                s.map((x, j) => (j === i ? { ...x, birth_weight: e.target.value } : x)),
                              )
                            }
                            className="w-32"
                          />
                        </div>
                        <label className="flex items-center gap-2 pb-2 text-[12.5px] text-[var(--sd-muted)]">
                          <input
                            type="checkbox"
                            checked={c.is_stillborn}
                            onChange={(e) =>
                              setCalves((s) =>
                                s.map((x, j) =>
                                  j === i ? { ...x, is_stillborn: e.target.checked } : x,
                                ),
                              )
                            }
                          />
                          Stillborn
                        </label>
                        {calves.length > 1 && (
                          <button
                            type="button"
                            onClick={() => setCalves((s) => s.filter((_, j) => j !== i))}
                            aria-label={`Remove calf ${i + 1}`}
                            className="mb-2 text-[var(--sd-quiet)] transition-colors hover:text-[var(--sd-sev-critical)]"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => setCalves((s) => [...s, blankCalf()])}
                      className="inline-flex w-fit items-center gap-1.5 text-[12.5px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)]"
                    >
                      <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
                      Another calf
                    </button>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="c-remarks">Notes</Label>
                    <Textarea
                      id="c-remarks"
                      value={remarks}
                      onChange={(e) => setRemarks(e.target.value)}
                      placeholder="Assisted; cow and calf up within the hour."
                    />
                  </div>

                  {who.needed && (
                    <OperatorField operator={who.operator} onChange={who.setOperator} />
                  )}
                  <Button onClick={send} disabled={busy || who.needed}>
                    <Baby className="mr-2 h-4 w-4" strokeWidth={1.75} />
                    {busy
                      ? "Recording…"
                      : `Record the calving (${calves.length} calf${calves.length === 1 ? "" : "s"})`}
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </Page>
  );
}

function Destination({
  label,
  from,
  to,
  moving,
  reason,
}: {
  label: string;
  from?: string;
  to: string;
  moving: boolean;
  reason: string;
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 px-1 py-1.5 text-[12.5px]">
      <span className="font-medium text-[var(--sd-ink)]">{label}</span>
      {from && <span className="text-[var(--sd-muted)]">{from}</span>}
      <ArrowRight className="h-3.5 w-3.5 shrink-0 text-[var(--sd-quiet)]" strokeWidth={2} />
      <span className={cn(moving ? "font-medium text-[var(--sd-ink)]" : "text-[var(--sd-muted)]")}>
        {to}
      </span>
      <span className="text-[11.5px] text-[var(--sd-quiet)]">— {reason}</span>
    </div>
  );
}
