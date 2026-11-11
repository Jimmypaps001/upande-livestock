import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Plus, Save, X } from "lucide-react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { NutritionPanel } from "@/components/feeding/NutritionPanel";
import {
  RecipeModeBar, UnitPicker, usePercentMode, type ModeRow,
} from "@/components/feeding/RecipeMode";
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
import { expandConcentrates } from "@/lib/nutrition";
import {
  describeChange, getHerdRations, setHerdRation,
  type HerdRation, type HerdRations, type RationDifference,
} from "@/lib/herds";
import {
  doseForHerd, isDoseUom, kgTotal, toLine, unitLabel, type LineUnit,
} from "@/lib/ration-maths";
import { cn, fmt } from "@/lib/utils";

type EditRow = ModeRow;

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
 * weighs out. They may be typed as kilos per head and a share of it each, and
 * an additive as a dose a head in grams or millilitres, outside the 100%.
 *
 * A herd that mixes from raw (Herds > Concentrate) is offered raw feeds only.
 */
export function RationEditor() {
  const [data, setData] = useState<HerdRations | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [changes, setChanges] = useState<RationDifference[] | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [rows, setRows] = useState<EditRow[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const mode = usePercentMode(rows, setRows);

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
  // Off: this farm mixes straight from raw ingredients, so a line may name raw
  // feeds only. A made concentrate already in the recipe stays nameable so the
  // row does not blank, and is warned about below.
  const chosen = useMemo(() => herds.find((h) => h.herd === picked) || null, [herds, picked]);
  // Per herd: its own Concentrate setting, the farm's switch when it has none.
  const rawOnly = (chosen?.premanufacture ?? data?.premanufacture_concentrate) === false;

  // The edit starts as what the herd is actually fed, so "save" with nothing
  // touched is a no-op the server recognises rather than a new revision.
  useEffect(() => {
    if (!chosen) {
      setRows([]);
      setName("");
      return;
    }
    setRows(
      mode.seed(
        chosen.lines.map((l) => ({
          key: nextKey++,
          item_code: l.item_code,
          qty: String(l.qty),
          unit: (l.is_dose && isDoseUom(l.uom) ? l.uom : "kg") as LineUnit,
        })),
      ),
    );
    // Seeded with what the ration is called, blank for a herd that has none —
    // which is the field that lets that herd be given its first one at all.
    setName(chosen.ration_name || chosen.ration_item || "");
    setChanges(null);
  }, [chosen?.herd, chosen?.bom]);

  // The ration's kilos; a dose is outside them, as the BOM's quantity is.
  const total = kgTotal(rows);
  const heads = chosen?.heads ?? 0;
  const dirty =
    !!chosen &&
    (rows.length !== chosen.lines.length ||
      rows.some((r, i) => {
        const was = chosen.lines[i];
        return (
          !was ||
          was.item_code !== r.item_code ||
          Math.abs(was.qty - Number(r.qty)) > 0.0005 ||
          !!was.is_dose !== ((r.unit || "kg") !== "kg")
        );
      }));

  // The one line of a TMR the farm mixes itself. Read off the choices rather
  // than the saved line, so picking a different feed lights up straight away.
  const isConcentrate = (code: string) =>
    !!feeds.find((f) => f.value === code)?.is_concentrate;
  const labelOf = (code: string) => feeds.find((f) => f.value === code)?.label || code;
  const uomOf = (code: string) => feeds.find((f) => f.value === code)?.uom || "";

  const stranded = rawOnly ? rows.filter((r) => r.item_code && isConcentrate(r.item_code)) : [];

  async function expand() {
    const r = await expandConcentrates(rows.filter((x) => x.item_code && Number(x.qty) > 0).map(toLine));
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    setRows(
      mode.seed(
        r.lines.map((l) => ({
          key: nextKey++,
          item_code: l.item_code,
          qty: String(l.qty),
          unit: (l.dose_uom || "kg") as LineUnit,
        })),
      ),
    );
    toast(`Rewrote ${r.expanded.join(", ")} into its ingredients. Save to make it the recipe.`, "info");
  }

  useSaveShortcut(() => void save(), !!chosen && dirty && !busy && rows.length > 0);

  async function save() {
    if (!chosen) return;
    setBusy(true);
    const r = await setHerdRation({
      herd: chosen.herd,
      ration_item: name.trim() || chosen.ration_item || undefined,
      lines: rows.filter((x) => x.item_code && Number(x.qty) > 0).map(toLine),
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
              <CardTitle>{chosen ? `${chosen.herd} · TMR` : "Nothing selected"}</CardTitle>
              <CardDescription>
                {chosen
                  ? chosen.bom
                    ? `Total mixed ration · recipe ${chosen.bom}`
                    : "This herd has no TMR yet. Name one below and it is created."
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

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="r-name">TMR name</Label>
                  <Input
                    id="r-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Finishing group 1"
                  />
                  <p className="text-[12px] text-[var(--sd-muted)]">
                    {chosen.bom
                      ? "Renaming makes a new ration; the herd is moved onto it."
                      : "Naming this ration creates it and gives it to the herd."}
                  </p>
                </div>

                {stranded.length > 0 && (
                  <Notice tone="info">
                    <span className="flex flex-wrap items-center gap-3">
                      <span>
                        This farm no longer pre-manufactures concentrate, but this ration still
                        uses {stranded.map((r) => labelOf(r.item_code)).join(", ")}.
                      </span>
                      <Button variant="secondary" size="sm" onClick={() => void expand()}>
                        Expand into ingredients
                      </Button>
                    </span>
                  </Notice>
                )}

                <RecipeModeBar mode={mode} idPrefix="r" />

                <div className="flex flex-col gap-2">
                  <Label>What goes in, per head, per day</Label>
                  {rows.map((r, i) => (
                    <div
                      key={r.key}
                      className={
                        "flex flex-wrap items-end gap-3 rounded-[var(--sd-radius-lg)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)] " +
                        (isConcentrate(r.item_code)
                          ? "bg-[var(--sd-accent-soft,#eef4ff)] ring-1 ring-[var(--sd-accent,#3b82f6)]/30"
                          : "bg-[var(--sd-bg-soft)]")
                      }
                    >
                      <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
                        <Label htmlFor={`r-item-${r.key}`}>
                          Feed
                          {isConcentrate(r.item_code) ? (
                            <span className="ml-2 text-[11px] font-medium text-[var(--sd-accent,#3b82f6)]">
                              concentrate
                            </span>
                          ) : null}
                        </Label>
                        <Picker
                          id={`r-item-${r.key}`}
                          value={r.item_code}
                          onChange={(next) =>
                            setRows((s) =>
                              s.map((x, j) => (j === i ? { ...x, item_code: next } : x)),
                            )
                          }
                          options={feeds
                            .filter((f) => !rawOnly || !f.is_concentrate || f.value === r.item_code)
                            .map((f) => ({ value: f.value, label: f.label }))}
                          label="Feed"
                          placeholder="Choose a feed…"
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor={`r-unit-${r.key}`}>Unit</Label>
                        <UnitPicker
                          id={`r-unit-${r.key}`}
                          value={r.unit}
                          onChange={(unit) =>
                            setRows((s) => s.map((x, j) => (j === i ? { ...x, unit, pct: "" } : x)))
                          }
                        />
                      </div>
                      {mode.on && (r.unit || "kg") === "kg" ? (
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`r-pct-${r.key}`}>Share (%)</Label>
                          <Input
                            id={`r-pct-${r.key}`}
                            type="number"
                            min={0}
                            max={100}
                            step="any"
                            value={r.pct ?? ""}
                            onChange={(e) => mode.changePct(r.key, e.target.value)}
                            className="w-24 text-right tabular-nums"
                          />
                        </div>
                      ) : (
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`r-qty-${r.key}`}>
                            {(r.unit || "kg") === "kg" ? "Amount" : "Dose"}
                          </Label>
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
                      )}
                      <span className="pb-2 text-[11.5px] text-[var(--sd-quiet)]">
                        {(r.unit || "kg") !== "kg" ? (
                          <>
                            {unitLabel(r.unit!)} a head, outside the 100% ·{" "}
                            {doseForHerd(r.qty, r.unit as "Gram" | "Millilitre", heads)} for the herd
                          </>
                        ) : (
                          <>
                            {mode.on ? `${fmt(Number(r.qty) || 0)} ` : ""}kg ·{" "}
                            {fmt((Number(r.qty) || 0) * heads)} for the herd
                          </>
                        )}
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
                    {rows.some((r) => (r.unit || "kg") !== "kg") ? " · doses not included" : ""}
                  </span>
                  <span className="text-[15px] font-semibold tabular-nums text-[var(--sd-ink)]">
                    {fmt(total)} kg
                    <span className="ml-2 text-[12px] font-normal text-[var(--sd-muted)]">
                      · {fmt(total * heads)} kg for {heads} head
                    </span>
                  </span>
                </div>

                <NutritionPanel
                  perUnit="head per day"
                  lines={rows.filter((x) => x.item_code && Number(x.qty) > 0).map(toLine)}
                />

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
