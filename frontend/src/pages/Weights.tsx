import { useCallback, useEffect, useMemo, useState } from "react";
import { Scale } from "lucide-react";
import { DatePicker } from "@/components/DatePicker";
import { Notice } from "@/components/feeding/Notice";
import { STICKY_HEAD, ScrollTable } from "@/components/ScrollTable";
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
import { isError } from "@/lib/frappe";
import { getWeightOptions, recordWeights, type WeightOptions, type WeightRow } from "@/lib/events";
import { useOperator } from "@/lib/operator";
import { useSaveShortcut } from "@/lib/use-save-shortcut";
import { todayISO } from "@/lib/utils";

interface Entry {
  weight_kg: string;
  heart_girth_cm: string;
  bcs: string;
}

const EMPTY: Entry = { weight_kg: "", heart_girth_cm: "", bcs: "" };

/**
 * Weighing — one animal, a handful, or a herd through a crush.
 *
 * WEIGHING IS A MORNING, NOT A MOMENT. The scale goes up, the race fills, and
 * a hundred numbers get called out in an hour. A screen that took one animal
 * and one number meant the morning was written on paper and typed up later, or
 * more often not typed up at all.
 *
 * Pick who is being weighed, then type down the column. A row left blank is a
 * cow that did not get on the scale — she is skipped and reported as skipped,
 * not failed, because the two mean different things to whoever reads the
 * result.
 *
 * THE GIRTH TAPE IS A SECOND COLUMN, not a second screen. A calf gets a tape
 * and a cow gets the platform on the same morning; the record keeps which, and
 * the weight is worked out from the girth when only that was taken.
 */
export function Weights() {
  const [options, setOptions] = useState<WeightOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const toast = useToast();
  const who = useOperator(options?.employee);

  const [when, setWhen] = useState(todayISO());
  const [method, setMethod] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getWeightOptions();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setOptions(r);
    setMethod((m) => m || r.methods[0] || "");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const byName = useMemo(
    () => new Map((options?.animals ?? []).map((a) => [a.name, a])),
    [options],
  );

  const written = picked.filter((id) => {
    const e = entries[id] ?? EMPTY;
    return Number(e.weight_kg) > 0 || Number(e.heart_girth_cm) > 0;
  });
  const ready = !!method && written.length > 0 && !who.needed;

  useSaveShortcut(() => void send(), ready && !busy);

  function set(id: string, field: keyof Entry, value: string) {
    setEntries((s) => ({ ...s, [id]: { ...(s[id] ?? EMPTY), [field]: value } }));
  }

  async function send() {
    if (!ready) return;
    setBusy(true);
    const weights: WeightRow[] = written.map((id) => {
      const e = entries[id] ?? EMPTY;
      return {
        animal: id,
        weight_kg: Number(e.weight_kg) > 0 ? Number(e.weight_kg) : undefined,
        heart_girth_cm: Number(e.heart_girth_cm) > 0 ? Number(e.heart_girth_cm) : undefined,
        bcs: Number(e.bcs) > 0 ? Number(e.bcs) : undefined,
      };
    });
    const r = await recordWeights({
      event_date: when,
      method,
      measured_by: who.value,
      weights,
    });
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    // A round that half worked says so. Naming the refusals is the whole point
    // of weighing in batches: "84 of 86, these two would not take" is an
    // answer, "something went wrong" is not.
    if (r.failed.length) {
      toast(
        `${r.count} weighed. ${r.failed.length} would not take: ` +
          r.failed.map((f) => `${f.animal} — ${f.why}`).join("; "),
        "error",
      );
    } else {
      toast(
        `${r.count} weighed.` +
          (r.skipped.length ? ` ${r.skipped.length} left blank.` : ""),
      );
    }
    setEntries({});
    setPicked([]);
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Weights">
        What they weigh, and how it was arrived at — a platform and a girth tape
        are not the same number and the record says which.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>The weighing</CardTitle>
            <CardDescription>
              Pick who went through, then type down the column. A blank row is a
              cow that did not get on the scale.
            </CardDescription>
          </CardHeading>
          <CardTools>
            <RefreshButton onClick={load} loading={loading} label="the list" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-4 pt-0">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="w-when">Weighed on</Label>
              <DatePicker id="w-when" value={when} max={todayISO()} onChange={setWhen} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="w-method">How</Label>
              <Picker
                id="w-method"
                value={method}
                onChange={setMethod}
                options={options?.methods ?? []}
                label="How"
                className="w-[190px]"
              />
            </div>
            {who.mustAsk && <OperatorField operator={who.operator} onChange={who.setOperator} />}
          </div>

          <TargetPicker
            animals={options?.animals ?? []}
            herds={options?.herds ?? []}
            picked={picked}
            onChange={setPicked}
            label="Who went through"
          />

          {picked.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label>The numbers</Label>
              {/* Ninety-four animals through a crush is ninety-four rows, and
                  the button that records them is underneath. */}
              <ScrollTable className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] shadow-[var(--sd-shadow-inset)]">
                <table className="w-full min-w-[460px] border-collapse text-[13px]">
                  <thead className={STICKY_HEAD}>
                    <tr className="text-left text-[11px] uppercase tracking-[0.06em] text-[var(--sd-quiet)]">
                      <th className="px-3.5 py-2 font-medium">Animal</th>
                      <th className="px-3 py-2 text-right font-medium">Weight (kg)</th>
                      <th className="px-3 py-2 text-right font-medium">Girth (cm)</th>
                      <th className="px-3.5 py-2 text-right font-medium">Condition</th>
                    </tr>
                  </thead>
                  <tbody>
                    {picked.map((id) => {
                      const a = byName.get(id);
                      const e = entries[id] ?? EMPTY;
                      return (
                        <tr key={id} className="border-t border-[var(--sd-line)]">
                          <td className="px-3.5 py-1.5">
                            <span className="font-medium text-[var(--sd-ink)]">
                              {a?.label ?? id}
                            </span>
                            {a?.herd_label && (
                              <span className="ml-2 text-[11.5px] text-[var(--sd-quiet)]">
                                {a.herd_label}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 text-right">
                            <Input
                              aria-label={`Weight for ${a?.label ?? id}`}
                              type="number"
                              min={0}
                              step="0.1"
                              value={e.weight_kg}
                              onChange={(ev) => set(id, "weight_kg", ev.target.value)}
                              className="w-24 text-right tabular-nums"
                            />
                          </td>
                          <td className="px-3 py-1.5 text-right">
                            <Input
                              aria-label={`Heart girth for ${a?.label ?? id}`}
                              type="number"
                              min={0}
                              step="0.1"
                              value={e.heart_girth_cm}
                              onChange={(ev) => set(id, "heart_girth_cm", ev.target.value)}
                              className="w-24 text-right tabular-nums"
                            />
                          </td>
                          <td className="px-3.5 py-1.5 text-right">
                            <Input
                              aria-label={`Body condition for ${a?.label ?? id}`}
                              type="number"
                              min={0}
                              max={5}
                              step="0.25"
                              value={e.bcs}
                              onChange={(ev) => set(id, "bcs", ev.target.value)}
                              className="w-20 text-right tabular-nums"
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </ScrollTable>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={send} disabled={!ready || busy}>
              <Scale className="mr-2 h-4 w-4" strokeWidth={1.75} />
              {busy ? "Recording…" : `Record ${written.length || "…"} weight${written.length === 1 ? "" : "s"}`}
            </Button>
            {picked.length > 0 && written.length < picked.length && (
              <span className="text-[11.5px] text-[var(--sd-muted)]">
                {picked.length - written.length} left blank — they will be skipped.
              </span>
            )}
            {!picked.length && (
              <span className="text-[11.5px] text-[var(--sd-muted)]">
                Pick a herd, or the animals that went through.
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </Page>
  );
}
