import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ExternalLink, Loader2, Plus, Save, X } from "lucide-react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { NutritionPanel } from "@/components/feeding/NutritionPanel";
import {
  LockButton, RecipeTotalBar, UnitPicker, useRecipeBalance, type ModeRow,
} from "@/components/feeding/RecipeMode";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { RowsSkeleton } from "@/components/Loading";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { useToast } from "@/components/Toast";
import { concentrates, setConcentrate, type Concentrate } from "@/lib/feeding";
import { isError } from "@/lib/frappe";
import {
  describeChange, getHerdRations, setHerdRation,
  type FeedChoice, type HerdRations, type RationDifference,
} from "@/lib/herds";
import {
  expandConcentrates, livestockFeeds, type FeedLibrary, type LibraryFeed,
} from "@/lib/nutrition";
import {
  doseForHerd, isDoseUom, isWeighed, kgTotal, qtyForKilos, rowKilos, toLine, toNutrientLine,
  unitFromUom, unitLabel, type LineUnit,
} from "@/lib/ration-maths";
import { isKg, kgPerUnit, stockEquivalent, storeUnits, useFeedUnits, type UnitsMap } from "@/lib/units";
import { concentratesInUse } from "@/lib/roles";
import { hashParams } from "@/lib/router";
import { useSaveShortcut } from "@/lib/use-save-shortcut";
import { cn, fmt, num } from "@/lib/utils";

type Row = ModeRow;
let nextKey = 1;

/** What is being edited: a herd's standing ration, or a concentrate (a known
 *  one by item code, or `null` for a new one). */
type Selection =
  | { kind: "herd"; herd: string }
  | { kind: "concentrate"; item: string | null }
  | null;

type Baseline = { lines: Array<{ item_code: string; qty: number; unit: LineUnit }>; name: string };

/** The desk form for a feed: its record, or a new one already pointing at the item. */
function deskLink(f: LibraryFeed): string {
  return f.recorded
    ? `/app/livestock-feed/${encodeURIComponent(f.item_code)}`
    : `/app/livestock-feed/new?item=${encodeURIComponent(f.item_code)}`;
}

/** What a link to this page asked for: `?herd=X`, `?concentrate=X` or `?concentrate=new`. */
function selectionFromHash(): Selection {
  const p = hashParams();
  const herd = p.get("herd");
  if (herd) return { kind: "herd", herd };
  const c = p.get("concentrate");
  if (c) return { kind: "concentrate", item: c === "new" ? null : c };
  return null;
}

/** Kilos in one of a row's unit, when it is a store unit (Litre, BALE). */
function kgPerOf(units: UnitsMap, item: string, unit: LineUnit | undefined): number | null {
  return unit && unit !== "kg" && !isDoseUom(unit) ? kgPerUnit(units, item, unit) : null;
}

/**
 * The Ration Editor: THE one place a recipe is written.
 *
 * It used to be two screens — Feed Design and this one — that both edited a
 * herd's standing ration, each with half the tools. They are one now: the feed
 * library with its nutrient badges, recipe lines in kilos or as a share of
 * intake with per-head doses in grams or millilitres, the live nutrition panel
 * with its targets, a herd's ration loaded and saved as its standing ration,
 * and — only where concentrate is in use on this farm — a concentrate designed
 * and saved too. Mixing is not here: a herd's feed is mixed on Feeding (one
 * herd, or Manufacture all), a concentrate batch on the Concentrate page.
 *
 * NO APPROVAL, BY DESIGN. The herdsman, the manager or the nutritionist decides
 * what goes in the mixer; saving is the change. What it is not is an EDIT: a
 * submitted BOM seals, so saving supersedes the recipe with a new revision and
 * points the herd at it. Every feed run already posted still names the recipe
 * it was mixed from, which is the whole reason the old one is left alone.
 * Saving is offered only once something has changed, so a farm re-saving the
 * same mix every morning does not accumulate a BOM a day.
 *
 * THE PAGE SENDS FACTS. Every nutrition figure comes from `feed_nutrition`,
 * saving goes through `set_herd_ration` / `set_concentrate`, and what is saved
 * is kilogram lines and dose lines, as the BOM holds them. Lines are in the
 * units the RECIPE is written in — hay in kilograms even though the store
 * holds bales — because that is what the person at the mixer weighs out.
 *
 * A herd that mixes from raw (Herds > Concentrate, the farm's Pre-manufacture
 * Concentrate switch by default) is offered raw feeds only, and a ration that
 * still names a concentrate says so and can be rewritten from that
 * concentrate's own recipe.
 */
export function RationEditor() {
  const [data, setData] = useState<HerdRations | null>(null);
  const [library, setLibrary] = useState<FeedLibrary | null>(null);
  const [concList, setConcList] = useState<Concentrate[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const [sel, setSel] = useState<Selection>(selectionFromHash);
  const [rows, setRows] = useState<Row[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [changes, setChanges] = useState<RationDifference[] | null>(null);
  const toast = useToast();
  const mode = useRecipeBalance(rows, setRows);

  // Does this farm have a concentrate stage at all? The server's fresh answer
  // where it has given one, the page's bootstrap until then.
  const inUse =
    data?.any_premanufacture ?? library?.any_premanufacture ?? concentratesInUse();
  const farmOn = data?.premanufacture_concentrate ?? library?.premanufacture_concentrate ?? true;

  const load = useCallback(async () => {
    setLoading(true);
    const [hr, lib] = await Promise.all([getHerdRations(), livestockFeeds()]);
    setLoading(false);
    if (isError(hr)) {
      setFailure(hr.error);
      return;
    }
    setFailure(isError(lib) ? lib.error : null);
    setData(hr);
    if (!isError(lib)) setLibrary(lib);
  }, []);

  const loadConcentrates = useCallback(async () => {
    const r = await concentrates();
    setConcList(isError(r) ? [] : r.concentrates);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // The concentrates are priced against the stores, so they are only asked
  // for where the farm has a concentrate stage to show them in.
  useEffect(() => {
    if (inUse) void loadConcentrates();
  }, [inUse, loadConcentrates]);

  const herds = data?.herds ?? [];
  const choices: FeedChoice[] = data?.feeds ?? [];
  const chosenHerd = sel?.kind === "herd" ? herds.find((h) => h.herd === sel.herd) || null : null;
  const chosenConc =
    sel?.kind === "concentrate" && sel.item
      ? (concList ?? []).find((c) => c.item_code === sel.item) || null
      : null;
  const target: "ration" | "concentrate" = sel?.kind === "concentrate" ? "concentrate" : "ration";
  // Something the recipe can be saved to: a herd that exists, or a concentrate.
  const editing = !!chosenHerd || sel?.kind === "concentrate";

  // No concentrate stage on this farm: a link asking for one opens nothing.
  useEffect(() => {
    if (!inUse && sel?.kind === "concentrate") setSel(null);
  }, [inUse, sel]);

  // Whether THIS recipe may name a made concentrate: a herd's own setting for
  // its ration, the farm's reach for a concentrate or an unattached recipe.
  const switchOn = chosenHerd ? (chosenHerd.premanufacture ?? farmOn) : inUse;

  const byCode = useMemo(() => {
    const m = new Map<string, LibraryFeed>();
    for (const f of library?.feeds ?? []) m.set(f.item_code, f);
    return m;
  }, [library]);
  const choiceByCode = useMemo(() => new Map(choices.map((c) => [c.value, c])), [choices]);

  const isConcentrate = useCallback(
    (code: string) =>
      !!code && (!!choiceByCode.get(code)?.is_concentrate || (byCode.get(code)?.is_made ?? false)),
    [byCode, choiceByCode],
  );
  const labelOf = (code: string) =>
    byCode.get(code)?.item_name || choiceByCode.get(code)?.label || code;
  const uomOf = (code: string) => choiceByCode.get(code)?.uom || "";

  // What the library offers. Off: raw feeds only. A ration is never an
  // ingredient of another one.
  const pickable = useMemo(
    () =>
      (library?.feeds ?? []).filter(
        (f) => f.category !== "Ration (made)" && (switchOn || !f.is_made),
      ),
    [library, switchOn],
  );

  // What a line may name: the library, the feeds nobody has described yet, and
  // every feed already in a recipe on this farm. A line already in the recipe
  // stays nameable even if the picker no longer offers it, so it does not blank.
  const options = useMemo(() => {
    const out = new Map<string, string>();
    for (const f of pickable) out.set(f.item_code, f.item_name);
    for (const u of library?.undescribed ?? []) out.set(u.item_code, `${u.item_name} (no data)`);
    for (const c of choices) {
      if (out.has(c.value) || (!switchOn && c.is_concentrate)) continue;
      out.set(c.value, c.label);
    }
    for (const r of rows) if (r.item_code && !out.has(r.item_code)) out.set(r.item_code, labelOf(r.item_code));
    return [...out].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label));
    // labelOf reads the same maps listed here.
  }, [pickable, library, choices, switchOn, rows, byCode, choiceByCode]);

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    const all = [
      ...pickable,
      ...(library?.undescribed ?? []).map(
        (u) => ({ ...u, category: null, recorded: false, is_made: false, nutrient_source: null, dry_matter_pct: 0,
                  cp_pct: 0, carbohydrate_pct: 0, ndf_pct: 0, fat_pct: 0, me_mj_per_kg: 0 }) as LibraryFeed,
      ),
    ];
    return all.filter((f) => !q || f.item_name.toLowerCase().includes(q));
  }, [pickable, library, search]);

  // What the recipe was when it was loaded, so "save" with nothing touched is
  // not offered — the server would recognise it, but a no-op is cheaper here.
  const baseline: Baseline = useMemo(() => {
    if (chosenHerd)
      return {
        lines: chosenHerd.lines.map((l) => ({
          item_code: l.item_code, qty: l.qty, unit: unitFromUom(l.uom, l.is_dose),
        })),
        name: chosenHerd.ration_name || chosenHerd.ration_item || "",
      };
    if (chosenConc)
      return {
        lines: chosenConc.lines.map((l) => ({
          item_code: l.item_code, qty: l.recipe_qty, unit: unitFromUom(l.recipe_uom),
        })),
        name: chosenConc.item_name,
      };
    return { lines: [], name: "" };
  }, [chosenHerd, chosenConc]);

  // Seed the recipe whenever a different thing is picked, or the one picked is
  // saved as a new revision (its BOM changes).
  const seedKey = `${sel?.kind ?? ""}:${sel?.kind === "herd" ? sel.herd : sel?.kind === "concentrate" ? sel.item : ""}:${
    chosenHerd?.bom ?? chosenConc?.bom_no ?? ""
  }`;
  // Every feed on screen, with the units it may be written in and their kilos.
  const units = useFeedUnits(
    useMemo(
      () => [...rows.map((r) => r.item_code), ...baseline.lines.map((l) => l.item_code)].filter(Boolean),
      [rows, baseline],
    ),
    data?.units,
  );

  useEffect(() => {
    setRows(
      mode.seed(
        baseline.lines.map((l) => ({
          key: nextKey++,
          item_code: l.item_code,
          qty: String(l.qty),
          unit: l.unit,
          kgPer: kgPerOf(units, l.item_code, l.unit),
        })),
      ),
    );
    setName(baseline.name);
  }, [seedKey]);

  // A store unit's kilos arrive with the units: fill them in on the rows, so
  // the sums, the percentages and the nutrition run on kilos.
  useEffect(() => {
    setRows((s) => {
      let changed = false;
      const out = s.map((r) => {
        const k = kgPerOf(units, r.item_code, r.unit);
        if (k === (r.kgPer ?? null)) return r;
        changed = true;
        return { ...r, kgPer: k };
      });
      return changed ? out : s;
    });
  }, [units, rows.length]);

  /** A line written in another unit: the kilos stay, the quantity follows. */
  function changeUnit(index: number, unit: LineUnit) {
    mode.settle(
      rows.map((x, j) => {
        if (j !== index) return x;
        const next = { ...x, unit, kgPer: kgPerOf(units, x.item_code, unit) };
        const convertible = unit === "kg" || !!next.kgPer;
        if (isWeighed(x) && isWeighed(next) && convertible && num(x.qty) > 0) {
          next.qty = String(qtyForKilos(next, rowKilos(x)));
        } else {
          // Its kilos changed (or it became a dose): it is not held any more.
          next.pct = "";
          next.locked = false;
        }
        return next;
      }),
    );
  }

  const lines = rows.filter((r) => r.item_code && num(r.qty) > 0).map(toLine);
  // What the nutrition panel weighs: kilos, a store unit at its kilo equivalent.
  const nutrientLines = rows.filter((r) => r.item_code && num(r.qty) > 0).map(toNutrientLine);
  // The recipe's kilos: doses are outside them, as the BOM's quantity is.
  const total = kgTotal(rows);
  const heads = chosenHerd?.heads ?? 0;
  const dirty =
    rows.length !== baseline.lines.length ||
    rows.some((r, i) => {
      const was = baseline.lines[i];
      return (
        !was ||
        was.item_code !== r.item_code ||
        Math.abs(was.qty - num(r.qty)) > 0.0005 ||
        was.unit !== (r.unit || "kg")
      );
    }) ||
    (!!name.trim() && name.trim() !== baseline.name);

  // A made concentrate in a recipe that may no longer name one.
  const stranded = !switchOn ? rows.filter((r) => isConcentrate(r.item_code)) : [];

  function pick(next: Selection) {
    setSel(next);
    setChanges(null);
  }

  /** Point one line at `code`, merging into a line that already has it (kg summed). */
  function pickFor(index: number, code: string) {
    const s = rows;
    const dup = s.findIndex(
      (r, j) => j !== index && r.item_code === code && (r.unit || "kg") === (s[index].unit || "kg"),
    );
    if (dup < 0 || !code) {
      setRows(s.map((x, j) => (j === index ? { ...x, item_code: code } : x)));
      return;
    }
    // Merged: the two lines' kilos together, unlocked, so its % is worked out again.
    const sum = num(s[dup].qty) + num(s[index].qty);
    mode.settle(
      s
        .map((x, j) => (j === dup ? { ...x, qty: sum ? String(sum) : "", locked: false } : x))
        .filter((_, j) => j !== index),
    );
  }

  function addFeed(code: string) {
    const have = rows.find((r) => r.item_code === code);
    if (have) {
      // Already in the recipe: take the person to that line, not a second one.
      const el = document.getElementById(`re-qty-${have.key}`) as HTMLInputElement | null;
      el?.focus();
      el?.select();
      return;
    }
    setRows((s) => {
      const empty = s.find((r) => !r.item_code);
      if (empty) return s.map((r) => (r === empty ? { ...r, item_code: code } : r));
      return [...s, { key: nextKey++, item_code: code, qty: "" }];
    });
  }

  async function expand() {
    const r = await expandConcentrates(nutrientLines);
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

  /** Beside a weighed line: the other unit's figure (kilos for a store
   *  unit, the store's unit for kilos), and what the herd gets. */
  function weighedHint(r: Row): string {
    const unit = r.unit || "kg";
    const kilos = rowKilos(r);
    const parts: string[] = [];
    if (unit === "kg") {
      const eq = num(r.qty) > 0 ? stockEquivalent(units, r.item_code, kilos) : null;
      if (eq) parts.push(`≈ ${fmt(eq.qty)} ${eq.uom}`);
      else if (uomOf(r.item_code) && !isKg(uomOf(r.item_code))) parts.push(`stocked in ${uomOf(r.item_code)}`);
    } else if (r.kgPer) {
      parts.push(`${num(r.qty)} ${unit} ≈ ${fmt(kilos)} kg`);
    } else {
      parts.push(`no kilo figure for ${unit} — counted as kilos; add it to the item's UOM conversions`);
    }
    if (chosenHerd) parts.push(`${fmt(kilos * heads)} kg for the herd`);
    return parts.join(" · ");
  }

  const canSave =
    !busy &&
    editing &&
    lines.length > 0 &&
    dirty &&
    (target === "ration" ? !!chosenHerd : !!name.trim());

  useSaveShortcut(() => void save(), canSave);

  async function save() {
    if (!canSave) return;
    setBusy(true);
    if (target === "ration" && chosenHerd) {
      const r = await setHerdRation({
        herd: chosenHerd.herd,
        ration_item: name.trim() || chosenHerd.ration_item || undefined,
        lines,
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
          ? `${chosenHerd.herd} now eats ${fmt(r.per_head_kg)} kg a head — ${fmt(r.day_kg)} kg a day. Recipe ${r.bom}${
              r.superseded ? `, superseding ${r.superseded}` : ""
            }.`
          : `Nothing changed — ${chosenHerd.herd} already eats exactly this.`,
        r.changed ? "ok" : "info",
      );
      void load();
      return;
    }
    const r = await setConcentrate({ name: name.trim(), lines });
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast(
      r.changed
        ? `${r.item} makes ${fmt(r.base_qty)} kg from these ingredients — recipe ${r.bom}.`
        : `Nothing changed — ${r.item} already says exactly this.`,
      r.changed ? "ok" : "info",
    );
    setSel({ kind: "concentrate", item: r.item });
    void loadConcentrates();
    void load();
  }

  const recipeTitle = chosenHerd
    ? `${chosenHerd.herd} · ration`
    : sel?.kind === "concentrate"
      ? chosenConc
        ? `${chosenConc.item_name} · concentrate`
        : "New concentrate"
      : "Nothing selected";

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Feeding" title="Ration Editor">
        What each herd eats, per head, per day
        {inUse ? " — and what goes into each concentrate the farm mixes" : ""}. Pick a herd
        {inUse ? " or a concentrate" : ""}, change the recipe with its nutrition in view, and save
        it. Saving makes a new revision; every feed run already posted keeps the recipe it was
        mixed from. The feed itself is mixed on Feeding
        {inUse ? ", and concentrate batches on Concentrate" : ""}.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}
      {!!changes?.length && (
        <Notice tone="info">{changes.map((c) => describeChange(c)).join("\n")}</Notice>
      )}

      <FigureRow>
        <Figure loading={!data} label="Herds fed" value={String(herds.filter((h) => h.bom).length)}
                hint={`of ${herds.length}`} />
        <Figure loading={!data} label="Without a ration" value={String(herds.filter((h) => !h.bom).length)}
                hint="nothing is mixed for them" />
        <Figure
          loading={!data} label="Whole farm"
          value={fmt(herds.reduce((s, h) => s + h.day_kg, 0))}
          unit="kg"
          hint="a day, at today's head counts"
        />
        {inUse && (
          <Figure loading={!concList} label="Concentrates" value={String(concList?.length ?? 0)}
                  hint="recipes the farm mixes" />
        )}
      </FigureRow>

      <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,300px)_minmax(0,1fr)_minmax(0,340px)]">
        {/* Left: what to edit, and what it can be made of. */}
        <div className="flex min-w-0 flex-col gap-5">
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
              {!data && <RowsSkeleton rows={6} />}
              <ul className="flex max-h-[360px] flex-col gap-1 overflow-auto">
                {herds.map((h) => (
                  <li key={h.herd}>
                    <button
                      type="button"
                      onClick={() => pick({ kind: "herd", herd: h.herd })}
                      aria-pressed={chosenHerd?.herd === h.herd}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
                        chosenHerd?.herd === h.herd ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
                      )}
                    >
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">{h.herd}</span>
                        <span className="text-[11.5px] tabular-nums text-[var(--sd-muted)]">
                          {h.bom ? `${fmt(h.per_head_kg)} kg × ${h.heads} head` : "no ration"}
                        </span>
                      </span>
                      {inUse && (h.premanufacture ?? farmOn) && (
                        <Badge variant="outline" title="Eats a pre-made concentrate (Herds > Concentrate)">
                          concentrate
                        </Badge>
                      )}
                      {!h.balanced && h.bom && (
                        <AlertTriangle className="h-4 w-4 shrink-0 text-[var(--sd-sev-critical)]" strokeWidth={1.75} />
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          {inUse && (
            <Card>
              <CardHeaderRow>
                <CardHeading>
                  <CardTitle>Concentrates</CardTitle>
                  <CardDescription>Mixes made for the store, by the batch.</CardDescription>
                </CardHeading>
              </CardHeaderRow>
              <CardContent className="flex flex-col gap-2 pt-0">
                {!concList && <Loader2 className="h-4 w-4 animate-spin" />}
                <ul className="flex flex-col gap-1">
                  {(concList ?? []).map((c) => (
                    <li key={c.item_code}>
                      <button
                        type="button"
                        onClick={() => pick({ kind: "concentrate", item: c.item_code })}
                        aria-pressed={chosenConc?.item_code === c.item_code}
                        className={cn(
                          "flex w-full flex-col rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
                          chosenConc?.item_code === c.item_code ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
                        )}
                      >
                        <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">{c.item_name}</span>
                        <span className="text-[11.5px] tabular-nums text-[var(--sd-muted)]">
                          {c.lines.length} ingredients · makes {fmt(c.base_qty)} {c.uom || "kg"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                <Button
                  variant="secondary"
                  size="sm"
                  className="self-start"
                  onClick={() => pick({ kind: "concentrate", item: null })}
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5" strokeWidth={2.5} />
                  New concentrate
                </Button>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeaderRow>
              <CardHeading>
                <CardTitle>Feed library</CardTitle>
                <CardDescription>Click a feed to add it to the recipe.</CardDescription>
              </CardHeading>
            </CardHeaderRow>
            <CardContent className="flex flex-col gap-3 pt-0">
              <Input
                aria-label="Search feeds"
                placeholder="Search feeds…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {!library && <Loader2 className="h-4 w-4 animate-spin" />}
              <ul className="flex max-h-[480px] flex-col gap-1 overflow-auto">
                {shown.map((f) => (
                  <li key={f.item_code}>
                    <div className="flex items-start gap-2 rounded-[var(--sd-radius-lg)] px-3 py-2.5 hover:bg-[var(--sd-bg-soft)]">
                      <button
                        type="button"
                        onClick={() => addFeed(f.item_code)}
                        disabled={!editing}
                        className="flex min-w-0 flex-1 flex-col items-start text-left disabled:cursor-default"
                        aria-label={`Add ${f.item_name}`}
                        title={editing ? undefined : "Pick a herd or a concentrate first"}
                      >
                        <span className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium text-[var(--sd-ink)]">
                          {f.item_name}
                          {f.is_made && <Badge variant="outline">made</Badge>}
                          {!f.has_data && <Badge variant="secondary">no data</Badge>}
                        </span>
                        <span className="text-[11.5px] tabular-nums text-[var(--sd-muted)]">
                          {f.category ? `${f.category} · ` : ""}
                          {f.has_data || f.is_made
                            ? `DM ${fmt(f.dry_matter_pct)}% · CP ${fmt(f.cp_pct)}% · carb ${fmt(f.carbohydrate_pct)}% · ME ${fmt(f.me_mj_per_kg)}`
                            : "nutrients not recorded"}
                        </span>
                      </button>
                      <a
                        href={deskLink(f)}
                        target="_blank"
                        rel="noreferrer"
                        title="Edit this feed in the desk"
                        className="mt-0.5 text-[var(--sd-quiet)] hover:text-[var(--sd-ink)]"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>
                  </li>
                ))}
                {library && shown.length === 0 && (
                  <li className="px-3 py-2 text-[13px] text-[var(--sd-muted)]">No feeds match.</li>
                )}
              </ul>
            </CardContent>
          </Card>
        </div>

        {/* Centre: the recipe. */}
        <Card className="self-start">
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>{recipeTitle}</CardTitle>
              <CardDescription>
                {chosenHerd
                  ? chosenHerd.bom
                    ? `What one animal eats in a day, as fed · recipe ${chosenHerd.bom}`
                    : "This herd has no ration yet. Name one below and it is created."
                  : sel?.kind === "concentrate"
                    ? chosenConc
                      ? `What goes into one batch, as fed · recipe ${chosenConc.bom_no}`
                      : "Name it and list what goes into one batch."
                    : inUse
                      ? "Pick a herd or a concentrate on the left."
                      : "Pick a herd on the left."}
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-4 pt-0">
            {!editing ? (
              <p className="text-[13px] text-[var(--sd-muted)]">
                A ration is what goes in the mixer for one animal for one day
                {inUse ? "; a concentrate is a mix made for the store, by the batch" : ""}.
              </p>
            ) : (
              <>
                {chosenHerd && !chosenHerd.balanced && chosenHerd.bom && (
                  <Notice tone="error">
                    This recipe says it makes {fmt(chosenHerd.per_head_kg)} kg while its
                    ingredients add up to {fmt(chosenHerd.lines_total)}. It issues less feed than
                    it consumes. Saving here puts the two back in step.
                  </Notice>
                )}

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="re-name">{target === "ration" ? "Ration name" : "Concentrate name"}</Label>
                  <Input
                    id="re-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={target === "ration" ? "e.g. Finishing group 1" : "e.g. Shoat Concentrate"}
                  />
                  <p className="text-[12px] text-[var(--sd-muted)]">
                    {target === "ration"
                      ? chosenHerd?.bom
                        ? "Renaming makes a new ration; the herd is moved onto it."
                        : "Naming this ration creates it and gives it to the herd."
                      : chosenConc
                        ? "Renaming makes a new concentrate; the old one stays as it is."
                        : "Naming it creates the concentrate the first time it is saved."}
                  </p>
                </div>

                {stranded.length > 0 && (
                  <Notice tone="info">
                    <span className="flex flex-wrap items-center gap-3">
                      <span>
                        {chosenHerd ? `${chosenHerd.herd} mixes from raw ingredients` : "This farm no longer pre-manufactures concentrate"},
                        but the recipe still uses {stranded.map((r) => labelOf(r.item_code)).join(", ")}.
                      </span>
                      <Button variant="secondary" size="sm" onClick={() => void expand()}>
                        Expand into ingredients
                      </Button>
                    </span>
                  </Notice>
                )}

                <RecipeTotalBar mode={mode} idPrefix="re" per={target === "ration" ? "head per day" : "batch"} />

                <div className="flex flex-col gap-2">
                  <Label>{target === "ration" ? "What goes in, per head, per day" : "What goes in, per batch"}</Label>
                  {rows.map((r, i) => {
                    const unit = r.unit || "kg";
                    const conc = isConcentrate(r.item_code);
                    return (
                      <div
                        key={r.key}
                        className={cn(
                          "flex flex-wrap items-end gap-3 rounded-[var(--sd-radius-lg)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]",
                          conc
                            ? "bg-[var(--sd-accent-soft,#eef4ff)] ring-1 ring-[var(--sd-accent,#3b82f6)]/30"
                            : "bg-[var(--sd-bg-soft)]",
                        )}
                      >
                        <div className="flex min-w-[200px] flex-1 flex-col gap-1.5">
                          <Label htmlFor={`re-item-${r.key}`}>
                            Feed
                            {conc ? (
                              <span className="ml-2 text-[11px] font-medium text-[var(--sd-accent,#3b82f6)]">
                                concentrate
                              </span>
                            ) : null}
                          </Label>
                          <Picker
                            id={`re-item-${r.key}`}
                            value={r.item_code}
                            onChange={(next) => pickFor(i, next)}
                            options={options}
                            label="Feed"
                            placeholder="Choose a feed…"
                          />
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`re-unit-${r.key}`}>Unit</Label>
                          <UnitPicker
                            id={`re-unit-${r.key}`}
                            value={r.unit}
                            onChange={(u) => changeUnit(i, u)}
                            storeUnits={storeUnits(units, r.item_code).map((o) => o.uom)}
                          />
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`re-qty-${r.key}`}>
                            {unit === "kg"
                              ? "Amount (kg)"
                              : isDoseUom(unit)
                                ? `Dose (${unitLabel(unit)} a head)`
                                : `Amount (${unit})`}
                          </Label>
                          <Input
                            id={`re-qty-${r.key}`}
                            type="number"
                            min={0}
                            step="any"
                            className="w-28 text-right tabular-nums"
                            value={r.qty}
                            onChange={(e) => mode.editQty(r.key, e.target.value)}
                          />
                        </div>
                        {isWeighed(r) && (
                          <div className="flex flex-col gap-1.5">
                            <Label htmlFor={`re-pct-${r.key}`}>Share (%)</Label>
                            <Input
                              id={`re-pct-${r.key}`}
                              type="number"
                              min={0}
                              max={100}
                              step="any"
                              className="w-24 text-right tabular-nums"
                              value={mode.shares[i] ?? ""}
                              onChange={(e) => mode.editPct(r.key, e.target.value)}
                            />
                          </div>
                        )}
                        {isWeighed(r) && mode.definite && (
                          <LockButton
                            locked={!!r.locked}
                            label={labelOf(r.item_code) || "this feed"}
                            onClick={() => mode.toggleLock(r.key)}
                          />
                        )}
                        <span className="pb-2 text-[11.5px] tabular-nums text-[var(--sd-quiet)]">
                          {isDoseUom(unit)
                            ? `${unitLabel(unit)} a head, outside the 100%${
                                chosenHerd ? ` · ${doseForHerd(r.qty, unit, heads)} for the herd` : ""
                              }`
                            : weighedHint(r)}
                        </span>
                        <button
                          type="button"
                          onClick={() => mode.settle(rows.filter((_, j) => j !== i))}
                          aria-label={`Take ${labelOf(r.item_code) || "this feed"} out`}
                          className="mb-2 text-[var(--sd-quiet)] transition-colors hover:text-[var(--sd-sev-critical)]"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() => setRows((s) => [...s, { key: nextKey++, item_code: "", qty: "" }])}
                    className="inline-flex w-fit items-center gap-1.5 text-[12.5px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)]"
                  >
                    <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
                    Another feed
                  </button>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3 shadow-[var(--sd-shadow-inset)]">
                  <span className="text-[12.5px] text-[var(--sd-muted)]">
                    {target === "ration" ? "One head, one day" : "One batch"}
                    {rows.some((r) => isDoseUom(r.unit)) ? " · doses not included" : ""}
                  </span>
                  <span className="text-[15px] font-semibold tabular-nums text-[var(--sd-ink)]">
                    {fmt(total)} kg
                    {chosenHerd && (
                      <span className="ml-2 text-[12px] font-normal text-[var(--sd-muted)]">
                        · {fmt(total * heads)} kg for {heads} head
                      </span>
                    )}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <Button onClick={() => void save()} disabled={!canSave}>
                    <Save className="mr-2 h-4 w-4" strokeWidth={1.75} />
                    {busy
                      ? "Saving…"
                      : chosenHerd
                        ? `Save as the ${chosenHerd.herd} ration`
                        : "Save the concentrate"}
                  </Button>
                  <Button variant="secondary" onClick={() => setRows(mode.seed([]))} disabled={!rows.length}>
                    Start blank
                  </Button>
                  <span className="text-[11.5px] text-[var(--sd-muted)]">
                    {dirty
                      ? "Saving makes a new revision; the old recipe stays readable."
                      : "Nothing has changed yet."}
                  </span>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Right: what is in it. */}
        <NutritionPanel
          lines={nutrientLines}
          perUnit={target === "ration" ? "head per day" : "batch"}
          className="self-start"
        />
      </div>
    </Page>
  );
}
