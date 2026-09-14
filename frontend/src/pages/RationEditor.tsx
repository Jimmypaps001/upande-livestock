import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Plus, Save, X } from "lucide-react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { RowsSkeleton } from "@/components/Loading";
import { useToast } from "@/components/Toast";
import { useSaveShortcut } from "@/lib/use-save-shortcut";
import { isError } from "@/lib/frappe";
import {
  describeChange, getHerdRations, setHerdRation,
  type HerdRation, type HerdRations, type RationDifference,
} from "@/lib/herds";
import { cn, fmt } from "@/lib/utils";

interface EditRow {
  key: number;
  item_code: string;
  qty: string;
}

let nextKey = 1;

/**
 * Changing what a herd is fed.
 *
 * NO APPROVAL, BY DESIGN. The herdsman or the manager decides what goes in the
 * mixer; this is not a request for permission, it is the change. What it is
 * not is an EDIT: a submitted BOM seals, so saving supersedes the recipe with
 * a new revision and points the herd at it. Every feed run already posted
 * still names the recipe it was mixed from, which is the whole reason the old
 * one is left alone.
 *
 * A FEED THAT IS NOT AVAILABLE IS SUBSTITUTED HERE. There is no separate
 * substitution flow and there does not need to be: swapping silage for sorghum
 * is changing the mixture, and changing the mixture is this screen. The next
 * Work Order uses what the herd now points at.
 *
 * Lines are in the units the RECIPE is written in — hay in kilograms even
 * though the store holds bales — because that is what the person at the mixer
 * weighs out.
 */
export function RationEditor() {
  const [data, setData] = useState<HerdRations | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [changes, setChanges] = useState<RationDifference[] | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [rows, setRows] = useState<EditRow[]>([]);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getHerdRations();
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

  const herds = data?.herds ?? [];
  const feeds = data?.feeds ?? [];
  const chosen = useMemo(() => herds.find((h) => h.herd === picked) || null, [herds, picked]);

  // The edit starts as what the herd is actually fed, so "save" with nothing
  // touched is a no-op the server recognises rather than a new revision.
  useEffect(() => {
    if (!chosen) {
      setRows([]);
      return;
    }
    setRows(
      chosen.lines.map((l) => ({ key: nextKey++, item_code: l.item_code, qty: String(l.qty) })),
    );
    setChanges(null);
  }, [chosen?.herd, chosen?.bom]);

  const total = rows.reduce((s, r) => s + (Number(r.qty) || 0), 0);
  const heads = chosen?.heads ?? 0;
  const dirty =
    !!chosen &&
    (rows.length !== chosen.lines.length ||
      rows.some((r, i) => {
        const was = chosen.lines[i];
        return !was || was.item_code !== r.item_code || Math.abs(was.qty - Number(r.qty)) > 0.0005;
      }));

  const labelOf = (code: string) => feeds.find((f) => f.value === code)?.label || code;
  const uomOf = (code: string) => feeds.find((f) => f.value === code)?.uom || "";

  useSaveShortcut(() => void save(), !!chosen && dirty && !busy && rows.length > 0);

  async function save() {
    if (!chosen) return;
    setBusy(true);
    const r = await setHerdRation({
      herd: chosen.herd,
      ration_item: chosen.ration_item || undefined,
      lines: rows
        .filter((x) => x.item_code && Number(x.qty) > 0)
        .map((x) => ({ item_code: x.item_code, qty: Number(x.qty) })),
    });
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      setChanges(null);
      return;
    }
    setChanges(r.differences);
    toast(
      r.changed
        ? `${chosen.herd} now eats ${fmt(r.per_head_kg)} kg a head — ${fmt(r.day_kg)} kg a day. Recipe ${r.bom}${r.superseded ? `, superseding ${r.superseded}` : ""}.`
        : `Nothing changed — ${chosen.herd} already eats exactly this.`,
      r.changed ? "ok" : "info",
    );
    void load();
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Feeding" title="Rations">
        What each herd is fed, per head, per day. Changing it makes a new
        revision and points the herd at it — the old one stays readable, because
        every feed run already posted names the recipe it was mixed from.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}
      {!!changes?.length && (
        <Notice tone="info">
          {changes.map((c) => describeChange(c)).join("\n")}
        </Notice>
      )}

      <FigureRow>
        <Figure loading={!data} label="Herds fed" value={String(herds.filter((h) => h.bom).length)}
                hint={`of ${herds.length}`} />
        <Figure loading={!data} label="Without a ration" value={String(herds.filter((h) => !h.bom).length)}
                hint="nothing is mixed for them" />
        <Figure loading={!data} label="Feeds in use" value={String(feeds.length)} hint="named in a recipe" />
        <Figure
          loading={!data} label="Whole farm"
          value={fmt(herds.reduce((s, h) => s + h.day_kg, 0))}
          unit="kg"
          hint="a day, at today's head counts"
        />
      </FigureRow>

      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Herds</CardTitle>
              <CardDescription>What each one eats a head, a day.</CardDescription>
            </CardHeading>
            <CardTools>
              <RefreshButton onClick={load} loading={loading} label="the rations" />
            </CardTools>
          </CardHeaderRow>
          <CardContent className="pt-0">
            {!data && <RowsSkeleton rows={8} />}
            <ul className="flex flex-col gap-1">
              {herds.map((h) => (
                <li key={h.herd}>
                  <button
                    type="button"
                    onClick={() => setPicked(h.herd)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
                      h.herd === picked ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
                    )}
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                        {h.herd}
                      </span>
                      <span className="text-[11.5px] tabular-nums text-[var(--sd-muted)]">
                        {h.bom
                          ? `${fmt(h.per_head_kg)} kg × ${h.heads} head`
                          : "no ration"}
                      </span>
                    </span>
                    {!h.balanced && h.bom && (
                      <AlertTriangle
                        className="h-4 w-4 shrink-0 text-[var(--sd-sev-critical)]"
                        strokeWidth={1.75}
                      />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>{chosen ? chosen.herd : "Nothing selected"}</CardTitle>
              <CardDescription>
                {chosen
                  ? chosen.bom
                    ? `${chosen.ration_name} · recipe ${chosen.bom}`
                    : "This herd has no ration yet."
                  : "Pick a herd on the left."}
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-4 pt-0">
            {!chosen ? (
              <p className="text-[13px] text-[var(--sd-muted)]">
                A ration is what goes in the mixer for one animal for one day.
              </p>
            ) : (
              <>
                {!chosen.balanced && chosen.bom && (
                  <Notice tone="error">
                    This recipe says it makes {fmt(chosen.per_head_kg)} kg while its
                    ingredients add up to {fmt(chosen.lines_total)}. It issues less feed than
                    it consumes. Saving here puts the two back in step.
                  </Notice>
                )}

                <div className="flex flex-col gap-2">
                  <Label>What goes in, per head, per day</Label>
                  {rows.map((r, i) => (
                    <div
                      key={r.key}
                      className="flex flex-wrap items-end gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]"
                    >
                      <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
                        <Label htmlFor={`r-item-${r.key}`}>Feed</Label>
                        <Picker
                          id={`r-item-${r.key}`}
                          value={r.item_code}
                          onChange={(next) =>
                            setRows((s) =>
                              s.map((x, j) => (j === i ? { ...x, item_code: next } : x)),
                            )
                          }
                          options={feeds.map((f) => ({ value: f.value, label: f.label }))}
                          label="Feed"
                          placeholder="Choose a feed…"
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor={`r-qty-${r.key}`}>Amount</Label>
                        <Input
                          id={`r-qty-${r.key}`}
                          type="number"
                          min={0}
                          step="any"
                          value={r.qty}
                          onChange={(e) =>
                            setRows((s) =>
                              s.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)),
                            )
                          }
                          className="w-28 text-right tabular-nums"
                        />
                      </div>
                      <span className="pb-2 text-[11.5px] text-[var(--sd-quiet)]">
                        kg · {fmt((Number(r.qty) || 0) * heads)} for the herd
                        {uomOf(r.item_code) && uomOf(r.item_code) !== "Kilogram"
                          ? ` · stocked in ${uomOf(r.item_code)}`
                          : ""}
                      </span>
                      <button
                        type="button"
                        onClick={() => setRows((s) => s.filter((_, j) => j !== i))}
                        aria-label={`Take ${labelOf(r.item_code)} out of the ration`}
                        className="mb-2 text-[var(--sd-quiet)] transition-colors hover:text-[var(--sd-sev-critical)]"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      setRows((s) => [...s, { key: nextKey++, item_code: "", qty: "" }])
                    }
                    className="inline-flex w-fit items-center gap-1.5 text-[12.5px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)]"
                  >
                    <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
                    Another feed
                  </button>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3 shadow-[var(--sd-shadow-inset)]">
                  <span className="text-[12.5px] text-[var(--sd-muted)]">
                    One head, one day
                  </span>
                  <span className="text-[15px] font-semibold tabular-nums text-[var(--sd-ink)]">
                    {fmt(total)} kg
                    <span className="ml-2 text-[12px] font-normal text-[var(--sd-muted)]">
                      · {fmt(total * heads)} kg for {heads} head
                    </span>
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <Button onClick={save} disabled={busy || !dirty || !rows.length}>
                    <Save className="mr-2 h-4 w-4" strokeWidth={1.75} />
                    {busy ? "Saving…" : "Save as a new revision"}
                  </Button>
                  <span className="text-[11.5px] text-[var(--sd-muted)]">
                    {dirty
                      ? "The old recipe stays readable; the herd points at the new one."
                      : "Nothing has changed yet."}
                  </span>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}
