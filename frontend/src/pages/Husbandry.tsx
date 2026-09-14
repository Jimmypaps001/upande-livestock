import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Syringe, X } from "lucide-react";
import { DatePicker } from "@/components/DatePicker";
import { Notice } from "@/components/feeding/Notice";
import { OperatorField } from "@/components/events/OperatorField";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { TargetPicker } from "@/components/events/TargetPicker";
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
import { createHusbandryEvent, getHusbandryOptions, type HusbandryOptions } from "@/lib/events";
import { useOperator } from "@/lib/operator";
import { useSaveShortcut } from "@/lib/use-save-shortcut";
import { cn, fmt, todayISO } from "@/lib/utils";

interface DrugRow {
  key: number;
  item_code: string;
  qty: string;
}

let nextKey = 1;

/**
 * The routine rounds — dosing, dipping, trimming, dehorning.
 *
 * TWO THINGS THE OLD SCREEN COULD NOT DO, both of which the endpoint behind it
 * has always supported. It took one animal at a time, which made a vaccination
 * morning — a herd through a crush — the one job the app was no use for. And it
 * asked for no drug at all, so the medicine went out of the store in somebody's
 * head and the withdrawal date went nowhere.
 *
 * THE DOSE IS PER ANIMAL, and the screen says so beside the total it will take
 * out of the store. 2 ml each across ninety head is 180 ml, and the difference
 * between typing one and meaning the other is a bottle.
 *
 * The round fans out into one event per animal on the server, because a
 * withdrawal date and a next-due date are facts about a cow and not about a
 * pen. Only the stock side is batched.
 */
export function Husbandry() {
  const [options, setOptions] = useState<HusbandryOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const toast = useToast();
  const who = useOperator(options?.employee);

  const [kind, setKind] = useState("");
  const [when, setWhen] = useState(todayISO());
  const [picked, setPicked] = useState<string[]>([]);
  const [drugs, setDrugs] = useState<DrugRow[]>([]);
  const [remarks, setRemarks] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getHusbandryOptions();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setOptions(r);
    setKind((current) => current || r.event_types[0] || "");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const takesDrugs = !!kind && (options?.drug_consuming_types ?? []).includes(kind);

  // A round that consumes nothing should not be carrying empty drug rows, and
  // one that does should start with a line rather than a button to find.
  useEffect(() => {
    setDrugs((rows) =>
      takesDrugs ? (rows.length ? rows : [{ key: nextKey++, item_code: "", qty: "" }]) : [],
    );
  }, [takesDrugs]);

  const ready = !!kind && picked.length > 0 && !who.needed;
  // THE BASKET. Every line that will leave the store, consolidated — the same
  // drug on two rows is one withdrawal from the store and has to be checked
  // against the balance as one, or two rows of 60 against a stock of 100 both
  // look affordable and the issue fails at the counter.
  const basket = useMemo(() => {
    const held = new Map<
      string,
      { item_code: string; name: string; each: number; all: number; have: number | null; uom: string }
    >();
    for (const d of drugs) {
      const qty = Number(d.qty);
      if (!d.item_code || !(qty > 0)) continue;
      const item = options?.drug_items.find((i) => i.value === d.item_code);
      const line = held.get(d.item_code) ?? {
        item_code: d.item_code,
        name: item?.item_name || d.item_code,
        each: 0,
        all: 0,
        have: item?.qty ?? null,
        uom: item?.uom || "",
      };
      line.each += qty;
      line.all += qty * picked.length;
      held.set(d.item_code, line);
    }
    return [...held.values()];
  }, [drugs, picked.length, options]);

  const short = basket.filter((b) => b.have != null && b.all > b.have);

  useSaveShortcut(() => void send(), ready && !busy);

  async function send() {
    if (!ready) return;
    setBusy(true);
    const r = await createHusbandryEvent({
      event_type: kind,
      animals: picked,
      event_date: when,
      operator: who.value,
      remarks: remarks.trim() || undefined,
      source_warehouse: options?.drug_warehouse || undefined,
      drugs: drugs
        .filter((d) => d.item_code && Number(d.qty) > 0)
        .map((d) => ({ item_code: d.item_code, qty: Number(d.qty) })),
    });
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast(
      `${kind} recorded for ${picked.length} animal${picked.length === 1 ? "" : "s"}.` +
        (basket.length
          ? ` ${basket.map((b) => `${fmt(b.all)} ${b.uom} ${b.name}`.trim()).join(", ")} issued.`
          : ""),
    );
    setPicked([]);
    setRemarks("");
    void load();
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Husbandry">
        The routine rounds. Pick a herd or the animals that were actually
        brought, say what each one got, and the store issues the total.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>What was done</CardTitle>
            <CardDescription>
              One event is written per animal — a withdrawal date is a fact about a
              cow, not about a pen.
            </CardDescription>
          </CardHeading>
          <CardTools>
            <RefreshButton onClick={load} loading={loading} label="the list" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-4 pt-0">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="h-kind">The job</Label>
              <Picker
                id="h-kind"
                value={kind}
                onChange={setKind}
                options={options?.event_types ?? []}
                label="The job"
                className="w-[190px]"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="h-when">Done on</Label>
              <DatePicker id="h-when" value={when} max={todayISO()} onChange={setWhen} />
            </div>
            {who.mustAsk && (
              <OperatorField operator={who.operator} onChange={who.setOperator} />
            )}
          </div>

          <TargetPicker
            animals={options?.animals ?? []}
            herds={options?.herds ?? []}
            picked={picked}
            onChange={setPicked}
          />

          {takesDrugs && (
            <div className="flex flex-col gap-2">
              <Label>What each animal got</Label>
              <p className="-mt-1 text-[11.5px] text-[var(--sd-quiet)]">
                Quantities are per animal. The basket underneath is what actually
                leaves the store.
              </p>
              {drugs.map((d, i) => (
                <div
                  key={d.key}
                  className="flex flex-wrap items-end gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]"
                >
                  <div className="flex min-w-[240px] flex-1 flex-col gap-1.5">
                    <Label htmlFor={`h-drug-${d.key}`}>From the store</Label>
                    <Picker
                      id={`h-drug-${d.key}`}
                      value={d.item_code}
                      onChange={(next) =>
                        setDrugs((s) =>
                          s.map((x, j) => (j === i ? { ...x, item_code: next } : x)),
                        )
                      }
                      options={(options?.drug_items ?? []).map((x) => ({
                        value: x.value,
                        label: x.label,
                      }))}
                      label="Drug"
                      placeholder="Choose a drug…"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`h-qty-${d.key}`}>Each</Label>
                    <Input
                      id={`h-qty-${d.key}`}
                      type="number"
                      min={0}
                      step="any"
                      value={d.qty}
                      onChange={(e) =>
                        setDrugs((s) => s.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))
                      }
                      className="w-28 text-right tabular-nums"
                    />
                  </div>
                  <DrugTotal
                    item={options?.drug_items.find((x) => x.value === d.item_code)}
                    each={Number(d.qty || 0)}
                    head={picked.length}
                  />
                  {drugs.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setDrugs((s) => s.filter((_, j) => j !== i))}
                      aria-label="Take this drug off the round"
                      className="mb-2 text-[var(--sd-quiet)] transition-colors hover:text-[var(--sd-sev-critical)]"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                onClick={() => setDrugs((s) => [...s, { key: nextKey++, item_code: "", qty: "" }])}
                className="inline-flex w-fit items-center gap-1.5 text-[12.5px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)]"
              >
                <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
                Another drug
              </button>
            </div>
          )}

          {takesDrugs && !!basket.length && (
            <div className="flex flex-col gap-2">
              <Label>Coming out of the store</Label>
              <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] shadow-[var(--sd-shadow-inset)]">
                <table className="w-full min-w-[420px] border-collapse text-[12.5px]">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-[0.06em] text-[var(--sd-quiet)]">
                      <th className="px-3.5 py-2 font-medium">Item</th>
                      <th className="px-3 py-2 text-right font-medium">Each</th>
                      <th className="px-3 py-2 text-right font-medium">Head</th>
                      <th className="px-3 py-2 text-right font-medium">Total out</th>
                      <th className="px-3.5 py-2 text-right font-medium">In store</th>
                    </tr>
                  </thead>
                  <tbody>
                    {basket.map((b) => {
                      const enough = b.have == null || b.all <= b.have;
                      return (
                        <tr key={b.item_code} className="border-t border-[var(--sd-line)]">
                          <td className="px-3.5 py-1.5 text-[var(--sd-ink)]">{b.name}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums text-[var(--sd-muted)]">
                            {fmt(b.each)} {b.uom}
                          </td>
                          <td className="px-3 py-1.5 text-right tabular-nums text-[var(--sd-muted)]">
                            {picked.length}
                          </td>
                          <td
                            className={cn(
                              "px-3 py-1.5 text-right font-medium tabular-nums",
                              enough ? "text-[var(--sd-ink)]" : "text-[var(--sd-sev-critical)]",
                            )}
                          >
                            {fmt(b.all)} {b.uom}
                          </td>
                          <td
                            className={cn(
                              "px-3.5 py-1.5 text-right tabular-nums",
                              enough ? "text-[var(--sd-quiet)]" : "text-[var(--sd-sev-critical)]",
                            )}
                          >
                            {b.have == null ? "—" : `${fmt(b.have)} ${b.uom}`}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {!!short.length && (
                <p className="text-[11.5px] text-[var(--sd-sev-critical)]">
                  The store cannot cover {short.map((b) => b.name).join(", ")}. The
                  round will be refused at the counter rather than half issued —
                  cut the dose, cut the number of animals, or restock first.
                </p>
              )}
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="h-remarks">Notes</Label>
            <Textarea id="h-remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={send} disabled={!ready || busy}>
              <Syringe className="mr-2 h-4 w-4" strokeWidth={1.75} />
              {busy
                ? "Recording…"
                : `Record ${kind || "it"} for ${picked.length || "…"} animal${picked.length === 1 ? "" : "s"}`}
            </Button>
            {!picked.length && (
              <span className="text-[11.5px] text-[var(--sd-muted)]">
                Pick a herd, or the animals that were brought.
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </Page>
  );
}

/**
 * What the round will actually take out of the store, and whether it is there.
 *
 * THE DOSE IS PER ANIMAL AND THE STORE IS NOT. 2 ml each across ninety head is
 * 180 ml, and a bottle holding 100 is a round that stops half way down the
 * race. The stock the picker already knows about is worth checking here rather
 * than in the error the issue throws afterwards.
 */
function DrugTotal({
  item,
  each,
  head,
}: {
  item?: { qty?: number; uom?: string };
  each: number;
  head: number;
}) {
  const total = each * head;
  const short = item?.qty != null && total > item.qty;
  return (
    <span
      className={cn(
        "pb-2 text-[11.5px]",
        short ? "text-[var(--sd-sev-critical)]" : "text-[var(--sd-quiet)]",
      )}
    >
      × {head} = {fmt(total)} {item?.uom ?? ""} out of the store
      {short ? ` — only ${fmt(item?.qty ?? 0)} there` : ""}
    </span>
  );
}
