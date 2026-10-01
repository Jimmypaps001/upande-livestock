import { useCallback, useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { DatePicker } from "@/components/DatePicker";
import { Notice } from "@/components/feeding/Notice";
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
import { Picker, type PickerOption } from "@/components/ui/picker";
import { Textarea } from "@/components/ui/textarea";
import { OperatorField } from "@/components/events/OperatorField";
import { ItemsUsed, blankRow, type ItemRow } from "@/components/events/ItemsUsed";
import { useToast } from "@/components/Toast";
import { useSaveShortcut } from "@/lib/use-save-shortcut";
import { isError, type Envelope } from "@/lib/frappe";
import { useOperator } from "@/lib/operator";
import type { AnimalChoice, StockChoice } from "@/lib/events";
import { useBatchPlans } from "@/lib/use-batch-plans";
import { cn, todayISO } from "@/lib/utils";

/**
 * The shape every record-an-event screen has.
 *
 * Twelve screens were going to be twelve copies of "pick an animal, fill in
 * four fields, submit" — and twelve places for the animal list to stop being
 * the server's narrowed one, or for the date to default to today on a screen
 * the farm uses to catch up on last week. So it is one component and the
 * screens are its configuration.
 *
 * THE ANIMAL LIST IS WHAT THE SERVER OFFERED. No filtering happens here: the
 * options endpoints already exclude a weaner from the service list and a cow
 * with no open service from the diagnosis list, and re-deciding that on the
 * client is how the two answers drift apart.
 */

export type FieldKind = "text" | "number" | "select" | "date" | "notes";

/** What a select would actually submit, whether its options are labelled. */
function optionValues(spec: FieldSpec): string[] {
  return (spec.options ?? []).map((o) => (typeof o === "string" ? o : o.value));
}

export interface FieldSpec {
  name: string;
  label: string;
  kind: FieldKind;
  /** Options for a select. A field whose list is empty is not rendered.
   *  A labelled option carries a value distinct from what is shown — the straw
   *  picker sends an item code and shows "Semen Chico · 12 Nos in Westwood
   *  Dairy Store", which is the difference between choosing a straw and
   *  choosing a number. */
  options?: (PickerOption | string)[];
  placeholder?: string;
  hint?: string;
  /** What the field starts at. A select whose farm-configured answer is on the
   *  options endpoint should not make anybody choose it again. */
  value?: string;
  /** Said when the value is not `value`. The farm has a setting; a different
   *  answer is worth a word, not a refusal — so this warns and nothing else. */
  warnIfChanged?: string;
  required?: boolean;
  /** Sent even when blank — for a date the server keys its guards on. */
  always?: boolean;
  min?: number;
  step?: string;
  /** Start on the first option, and move when the options change underneath.
   *  For a select whose list BELONGS to another field: the stores holding a
   *  straw are the stores for THAT straw, so a value left from the previous
   *  one names a shelf that does not hold this one. The server orders these
   *  most-stocked first, so the first option is the store to go to. */
  autoPick?: boolean;
}

export interface RecordEventProps<O> {
  eyebrow: string;
  title: string;
  blurb: string;
  /** What the animal list is called on this screen, in the farm's words. */
  pickLabel: string;
  emptyPick: string;
  /** Loads the screen's options. */
  load: () => Promise<Envelope<O>>;
  /** Which animals this screen may act on, out of what `load` returned. */
  animalsOf: (options: O) => AnimalChoice[];
  /** The fields, which may depend on the options just loaded. */
  /** `values` is the form as it stands, so a field's options may depend on
   *  another field — the store list belongs to the straw that was chosen. */
  fieldsOf: (options: O, values: Record<string, string>) => FieldSpec[];
  /** The date field's name, if this screen has one. */
  dateField?: string;
  submitLabel: string;
  // Whatever else the endpoint answers rides along: a check-up that escalates
  // reports the file it opened, and the screen has to be able to say so.
  submit: (
    payload: Record<string, unknown>,
  ) => Promise<Envelope<{ name: string } & Record<string, unknown>>>;
  /** What to say after a successful submit. */
  said: (result: { name: string } & Record<string, unknown>, animal: string) => string;
  /** Anything extra to show once an animal is chosen — a preview, a warning. */
  aside?: (animal: AnimalChoice, options: O) => React.ReactNode;
  /** Who the server thinks is recording this, from the options endpoint. */
  operatorOf?: (options: O) => string | null;
  /** What this event may consume, if the farm mapped anything to its type.
   *  Absent: no table. `undefined` returned: not loaded, renders nothing.
   *  An explicit `[]` says nothing is mapped. */
  itemsOf?: (options: O) => StockChoice[] | undefined;
}

export function RecordEvent<O>({
  eyebrow,
  title,
  blurb,
  pickLabel,
  emptyPick,
  load,
  animalsOf,
  fieldsOf,
  dateField,
  submitLabel,
  submit,
  said,
  aside,
  operatorOf,
  itemsOf,
}: RecordEventProps<O>) {
  const [options, setOptions] = useState<O | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [term, setTerm] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});

  const [itemRows, setItemRows] = useState<ItemRow[]>(() => [blankRow()]);
  const plans = useBatchPlans(itemRows);

  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const who = useOperator(options && operatorOf ? operatorOf(options) : undefined);

  const refresh = useCallback(async () => {
    setLoading(true);
    const r = await load();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setOptions(r);

  }, [load, operatorOf]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const animals = options ? animalsOf(options) : [];
  const fields = useMemo(
    () => (options ? fieldsOf(options, values) : []),
    [options, fieldsOf, values],
  );

  // Defaults are seeded once per options load: a select with one sensible
  // answer should not make somebody choose it, and a date the farm is
  // back-filling should start at today rather than empty.
  useEffect(() => {
    if (!options) return;
    const seed: Record<string, string> = {};
    for (const f of fieldsOf(options, {})) {
      if (f.value) seed[f.name] = f.value;
      else if (f.kind === "date") seed[f.name] = todayISO();
      else if (f.kind === "select" && f.options?.length === 1)
        seed[f.name] = optionValues(f)[0];
    }
    setValues(seed);
  }, [options, fieldsOf]);

  // A dependent select follows its parent. Only ever written when the current
  // value is not on offer, so this cannot fight the operator for the field.
  useEffect(() => {
    setValues((prev) => {
      let next = prev;
      for (const f of fields) {
        if (f.kind !== "select" || !f.autoPick) continue;
        const vals = optionValues(f);
        if (!vals.length || vals.includes(prev[f.name] ?? "")) continue;
        if (next === prev) next = { ...prev };
        next[f.name] = vals[0];
      }
      return next;
    });
  }, [fields]);

  const chosen = animals.find((a) => a.name === picked) || null;
  const results = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return animals;
    return animals.filter((a) =>
      [a.name, a.label, a.herd_label || a.herd || ""].some((f) =>
        f.toLowerCase().includes(q),
      ),
    );
  }, [animals, term]);

  const missing = fields.filter((f) => f.required && !values[f.name]?.trim());
  // EVERY EVENT SAYS WHO RECORDED IT. The server refuses one that does not —
  // "Operator(technician) is mandatory for a hand-entered Livestock Event" —
  // and the options endpoint answers with the Employee linked to the signed-in
  // user, which for an administrator or a shared login is nobody. Asked for
  // here rather than discovered on submit.
  const needsOperator = !!operatorOf && who.needed;

  useSaveShortcut(
    () => void send(),
    !!picked && !busy && !missing.length && !needsOperator,
  );

  async function send() {
    if (!picked) return;
    setBusy(true);
    const payload: Record<string, unknown> = { animal: picked };
    if (who.value) payload.operator = who.value;
    for (const f of fields) {
      const v = values[f.name];
      if (v === undefined || v === "") {
        if (f.always) payload[f.name] = null;
        continue;
      }
      payload[f.name] = f.kind === "number" ? Number(v) : v;
    }
    if (itemsOf) {
      // Never an empty batch_no: an empty string reads as a batch named "".
      payload.items = itemRows
        .filter((r) => r.item && Number(r.qty) > 0)
        .map((r) => ({
          item_code: r.item,
          qty: Number(r.qty),
          source_warehouse: r.store,
          batch_no: r.batch || undefined,
        }));
    }
    const r = await submit(payload);
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast(said(r, picked));
    setPicked(null);
    setItemRows([blankRow()]);
    void refresh();
  }

  return (
    <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>{pickLabel}</CardTitle>
            <CardDescription>{blurb}</CardDescription>
          </CardHeading>
          <CardTools>
            <RefreshButton onClick={refresh} loading={loading} label="the list" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-3 pt-0">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--sd-quiet)]" />
            <Input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Number, name or herd…"
              aria-label={`Find an animal for ${title.toLowerCase()}`}
              className="h-10 rounded-[var(--sd-radius-pill)] border-[var(--sd-line)] bg-[var(--sd-bg-soft)] pl-9 text-[13px]"
            />
          </div>
          <p className="px-1 text-[11.5px] text-[var(--sd-quiet)]">
            {results.length === animals.length
              ? `${animals.length} offered`
              : `${results.length} of ${animals.length}`}
          </p>
          {!animals.length ? (
            <p className="text-[13px] text-[var(--sd-muted)]">{emptyPick}</p>
          ) : (
            <ul className="flex max-h-[420px] flex-col gap-1 overflow-y-auto">
              {results.map((a) => (
                <li key={a.name}>
                  <button
                    type="button"
                    onClick={() => setPicked(a.name)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
                      a.name === picked
                        ? "bg-[var(--sd-bg-soft)]"
                        : "hover:bg-[var(--sd-bg-soft)]",
                    )}
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                        {a.label}
                      </span>
                      <span className="truncate text-[11.5px] text-[var(--sd-muted)]">
                        {a.herd_label || a.herd || "no herd"}
                        {a.repro ? ` · ${a.repro}` : ""}
                      </span>
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
              {chosen
                ? `${chosen.herd_label || chosen.herd || "no herd"}${chosen.repro ? ` · ${chosen.repro}` : ""}`
                : `Pick one on the left to record ${title.toLowerCase()}.`}
            </CardDescription>
          </CardHeading>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-4 pt-0">
          {failure && <Notice tone="error">{failure}</Notice>}

          {!chosen ? (
            <p className="text-[13px] text-[var(--sd-muted)]">{blurb}</p>
          ) : (
            <>
              {aside && options ? aside(chosen, options) : null}
              <div className="grid gap-4 sm:grid-cols-2">
                {fields.map((f) => (
                  <Field
                    key={f.name}
                    spec={f}
                    value={values[f.name] ?? ""}
                    onChange={(v) => setValues((s) => ({ ...s, [f.name]: v }))}
                  />
                ))}
              </div>
              {itemsOf && options && (
                <ItemsUsed
                  choices={itemsOf(options)}
                  rows={itemRows}
                  onChange={setItemRows}
                  plans={plans}
                />
              )}
              {!!operatorOf && who.mustAsk && (
                <OperatorField operator={who.operator} onChange={who.setOperator} />
              )}
              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={send} disabled={busy || !!missing.length || needsOperator}>
                  {busy ? "Recording…" : submitLabel}
                </Button>
                {!!missing.length && (
                  <span className="text-[11.5px] text-[var(--sd-muted)]">
                    Still needs {missing.map((m) => m.label.toLowerCase()).join(", ")}.
                  </span>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  spec,
  value,
  onChange,
}: {
  spec: FieldSpec;
  value: string;
  onChange: (v: string) => void;
}) {
  const id = `f-${spec.name}`;
  if (spec.kind === "select" && !spec.options?.length) return null;
  return (
    <div className={cn("flex flex-col gap-1.5", spec.kind === "notes" && "sm:col-span-2")}>
      <Label htmlFor={id}>{spec.label}</Label>
      {spec.kind === "select" ? (
        <Picker
          id={id}
          value={value}
          onChange={onChange}
          options={spec.options!}
          label={spec.label}
          clearable={!spec.required}
          placeholder="—"
        />
      ) : spec.kind === "date" ? (
        <DatePicker id={id} value={value} max={todayISO()} onChange={onChange} />
      ) : spec.kind === "notes" ? (
        <Textarea
          id={id}
          value={value}
          placeholder={spec.placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <Input
          id={id}
          type={spec.kind === "number" ? "number" : "text"}
          min={spec.min}
          step={spec.step}
          value={value}
          placeholder={spec.placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {spec.hint && <span className="text-[11px] text-[var(--sd-quiet)]">{spec.hint}</span>}
      {/* The farm's own answer is the one that was offered; anything else is
          allowed and said out loud. Amber, not red: this is not a refusal. */}
      {spec.warnIfChanged && spec.value && value && value !== spec.value && (
        <span className="text-[11px] text-[var(--sd-sev-high)]">{spec.warnIfChanged}</span>
      )}
    </div>
  );
}
