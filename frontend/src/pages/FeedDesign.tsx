import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, Factory, Loader2, Plus, Save, X } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { NutritionPanel } from "@/components/feeding/NutritionPanel";
import {
  RecipeModeBar, UnitPicker, usePercentMode, type ModeRow,
} from "@/components/feeding/RecipeMode";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { useToast } from "@/components/Toast";
import { setConcentrate } from "@/lib/feeding";
import { isError } from "@/lib/frappe";
import { canMix } from "@/lib/roles";
import { getHerdRations, setHerdRation, type HerdRation } from "@/lib/herds";
import {
  expandConcentrates, livestockFeeds, manufactureAllFeeds,
  type AllFeeds, type FeedLibrary, type LibraryFeed,
} from "@/lib/nutrition";
import {
  doseForHerd, isDoseUom, kgTotal, toLine, unitLabel, type LineUnit,
} from "@/lib/ration-maths";
import { cn, fmt, num, todayISO } from "@/lib/utils";

type Row = ModeRow;
let nextKey = 1;

type Target = "ration" | "concentrate";

/** The desk form for a feed: its record, or a new one already pointing at the item. */
function deskLink(f: LibraryFeed): string {
  return f.recorded
    ? `/app/livestock-feed/${encodeURIComponent(f.item_code)}`
    : `/app/livestock-feed/new?item=${encodeURIComponent(f.item_code)}`;
}

/**
 * Feed Design: pick feeds, set quantities, see what is in the mix, save it,
 * and mix the day's feed for every herd.
 *
 * THE PAGE SENDS FACTS. Every nutrition figure comes from `feed_nutrition`,
 * the decision about what the stores can cover and which herds are still owed
 * feed comes from `manufacture_all_feeds`, and saving goes through the same
 * `set_herd_ration` / `set_concentrate` the other pages use. Nothing here
 * works out stock or money.
 *
 * A herd that mixes from raw (Herds > Concentrate, the farm's Pre-manufacture
 * Concentrate switch by default) has no concentrate stage: designing its
 * ration offers raw feeds only, and a ration that still names a concentrate
 * says so and can be rewritten from that concentrate's own recipe. The
 * concentrate target itself is offered while any herd still eats one.
 *
 * A ration may be typed as kilos per head and a percentage per line, and a
 * line may be a per-head dose in grams or millilitres outside the 100%. What
 * is saved is kilogram lines and dose lines, as the BOM holds them.
 *
 * On a farm that does not feed by head count, Manufacture all offers head
 * count x per head as a suggestion and mixes the totals the operator types.
 */
export function FeedDesign() {
  const [library, setLibrary] = useState<FeedLibrary | null>(null);
  const [herds, setHerds] = useState<HerdRation[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const [target, setTarget] = useState<Target>("ration");
  const [herd, setHerd] = useState("");
  const [name, setName] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);

  const [all, setAll] = useState<AllFeeds | null>(null);
  const [allOpen, setAllOpen] = useState(false);
  const [allBusy, setAllBusy] = useState(false);
  const [allDone, setAllDone] = useState<AllFeeds | null>(null);
  // The group totals typed on a farm that does not feed by head count.
  const [allTotals, setAllTotals] = useState<Record<string, string>>({});
  const toast = useToast();
  const mode = usePercentMode(rows, setRows);

  const load = useCallback(async () => {
    const [lib, hr] = await Promise.all([livestockFeeds(), getHerdRations()]);
    if (isError(lib)) {
      setFailure(lib.error);
      return;
    }
    setFailure(null);
    setLibrary(lib);
    if (!isError(hr)) setHerds(hr.herds);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const farmOn = library?.premanufacture_concentrate !== false;
  // Some herd still eats a pre-made concentrate: concentrates may be designed.
  const anyOn = library?.any_premanufacture ?? farmOn;
  const chosenHerd = herds.find((h) => h.herd === herd) || null;
  // Whether THIS recipe may name a concentrate: a herd's own setting for its
  // ration, the farm's reach for a concentrate or an unattached design.
  const switchOn =
    target === "ration" && chosenHerd ? (chosenHerd.premanufacture ?? farmOn) : anyOn;

  // What a line may name. Off: raw feeds only — the server says which are made.
  // A ration is never an ingredient of another one.
  const pickable = useMemo(() => {
    const out: LibraryFeed[] = [];
    for (const f of library?.feeds ?? []) {
      if (f.category === "Ration (made)") continue;
      if (f.is_made && !switchOn) continue;
      out.push(f);
    }
    return out;
  }, [library, switchOn]);

  const byCode = useMemo(() => {
    const m = new Map<string, LibraryFeed>();
    for (const f of library?.feeds ?? []) m.set(f.item_code, f);
    return m;
  }, [library]);

  const options = useMemo(() => {
    const base = [
      ...pickable.map((f) => ({ value: f.item_code, label: f.item_name })),
      ...(library?.undescribed ?? []).map((u) => ({ value: u.item_code, label: `${u.item_name} (no data)` })),
    ];
    // A line already in the recipe stays nameable even if the picker no longer
    // offers it, so the row does not blank out.
    for (const r of rows) {
      if (r.item_code && !base.some((o) => o.value === r.item_code)) {
        base.push({ value: r.item_code, label: byCode.get(r.item_code)?.item_name ?? r.item_code });
      }
    }
    return base.sort((a, b) => a.label.localeCompare(b.label));
  }, [pickable, library, rows, byCode]);

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

  function loadHerd(next: string) {
    setHerd(next);
    const h = herds.find((x) => x.herd === next);
    if (!h) return;
    setRows(
      mode.seed(
        h.lines.map((l) => ({
          key: nextKey++,
          item_code: l.item_code,
          qty: String(l.qty),
          unit: (l.is_dose && isDoseUom(l.uom) ? l.uom : "kg") as LineUnit,
        })),
      ),
    );
    setName(h.ration_name || h.ration_item || "");
  }

  /** Point one line at `code`, merging into a line that already has it (kg summed). */
  function pickFor(index: number, code: string) {
    setRows((s) => {
      const dup = s.findIndex(
        (r, j) => j !== index && r.item_code === code && (r.unit || "kg") === (s[index].unit || "kg"),
      );
      if (dup < 0 || !code) return s.map((x, j) => (j === index ? { ...x, item_code: code } : x));
      const sum = num(s[dup].qty) + num(s[index].qty);
      return s
        .map((x, j) => (j === dup ? { ...x, qty: sum ? String(sum) : "" } : x))
        .filter((_, j) => j !== index);
    });
  }

  function addFeed(code: string) {
    const have = rows.find((r) => r.item_code === code);
    if (have) {
      // Already in the recipe: take the person to that line, not a second one.
      const el = document.getElementById(`fd-qty-${have.key}`) as HTMLInputElement | null;
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

  const lines = rows.filter((r) => r.item_code && num(r.qty) > 0).map(toLine);
  // The ration's kilos: doses are outside them, as the BOM's quantity is.
  const total = kgTotal(rows);

  // A made concentrate in a recipe on a farm that no longer pre-mixes it.
  const stranded = !switchOn
    ? rows.filter((r) => r.item_code && byCode.get(r.item_code)?.is_made).map((r) => byCode.get(r.item_code)!)
    : [];

  async function expand() {
    const r = await expandConcentrates(lines);
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

  async function save() {
    setBusy(true);
    if (target === "ration") {
      if (!chosenHerd) {
        setBusy(false);
        toast("Choose the herd this ration is for.", "error");
        return;
      }
      const r = await setHerdRation({
        herd: chosenHerd.herd,
        ration_item: name.trim() || chosenHerd.ration_item || undefined,
        lines,
      });
      setBusy(false);
      if (isError(r)) {
        toast(r.error, "error");
        return;
      }
      toast(
        r.changed
          ? `${chosenHerd.herd} now eats ${fmt(r.per_head_kg)} kg a head — ${fmt(r.day_kg)} kg a day. Recipe ${r.bom}.`
          : `Nothing changed — ${chosenHerd.herd} already eats exactly this.`,
        r.changed ? "ok" : "info",
      );
    } else {
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
    }
    void load();
  }

  async function openAll() {
    setAllDone(null);
    setAll(null);
    setAllOpen(true);
    const r = await manufactureAllFeeds({ date: todayISO(), preview: true });
    if (isError(r)) {
      setAllOpen(false);
      toast(r.error, "error");
      return;
    }
    setAll(r);
    setAllTotals(Object.fromEntries(r.herds.map((h) => [h.herd, String(h.suggested_qty ?? h.qty)])));
  }

  // Off, the operator's totals are what is mixed; a herd left blank is not fed.
  const typingTotals = all?.feed_by_head_count === false;

  async function confirmAll() {
    setAllBusy(true);
    const totals = typingTotals
      ? Object.fromEntries(
          Object.entries(allTotals)
            .map(([h, v]) => [h, num(v)] as const)
            .filter(([, v]) => v > 0),
        )
      : undefined;
    const r = await manufactureAllFeeds({ date: todayISO(), totals });
    setAllBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    setAllDone(r);
    void load();
  }

  const canSave =
    !busy && lines.length > 0 && (target === "ration" ? !!chosenHerd : !!name.trim());

  return (
    <Page>
      <PageHeading
        eyebrow="Upande Livestock · Feeding"
        title="Feed Design"
        actions={
          // Mixing moves stock; the nutritionist designs and saves, Stores mixes.
          canMix() ? (
            <Button onClick={() => void openAll()} disabled={!library}>
              <Factory className="mr-2 h-4 w-4" strokeWidth={1.75} />
              Manufacture all
            </Button>
          ) : undefined
        }
      >
        Pick feeds, set the amounts, and see what is in the mix. Save it as a herd&rsquo;s ration
        {switchOn ? " or as a concentrate" : ""}, then mix every herd&rsquo;s feed for the day in
        one go.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,320px)_minmax(0,1fr)_minmax(0,340px)]">
        {/* Left: the library. */}
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Feed library</CardTitle>
              <CardDescription>Click a feed to add it to the recipe.</CardDescription>
            </CardHeading>
            <CardTools>
              <RefreshButton onClick={load} loading={!library} label="the feeds" />
            </CardTools>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-3 pt-0">
            <Input
              aria-label="Search feeds"
              placeholder="Search feeds…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {!library && <Loader2 className="h-4 w-4 animate-spin" />}
            <ul className="flex max-h-[560px] flex-col gap-1 overflow-auto">
              {shown.map((f) => (
                <li key={f.item_code}>
                  <div className="flex items-start gap-2 rounded-[var(--sd-radius-lg)] px-3 py-2.5 hover:bg-[var(--sd-bg-soft)]">
                    <button
                      type="button"
                      onClick={() => addFeed(f.item_code)}
                      className="flex min-w-0 flex-1 flex-col items-start text-left"
                      aria-label={`Add ${f.item_name}`}
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

        {/* Centre: the recipe. */}
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Recipe</CardTitle>
              <CardDescription>
                {target === "ration"
                  ? "What one animal eats in a day, as fed."
                  : "What goes into one batch of the mix, as fed."}
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-4 pt-0">
            <div className="flex flex-wrap items-end gap-3">
              {switchOn && (
                <div className="flex flex-col gap-1.5">
                  <Label>Designing</Label>
                  <div className="inline-flex overflow-hidden rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
                    {(["ration", "concentrate"] as const).map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setTarget(t)}
                        className={cn(
                          "px-3 py-1.5 text-[12.5px] font-medium",
                          target === t ? "bg-[var(--sd-ink)] text-white" : "text-[var(--sd-muted)]",
                        )}
                      >
                        {t === "ration" ? "A herd's ration" : "A concentrate"}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {target === "ration" && (
                <div className="flex min-w-[220px] flex-col gap-1.5">
                  <Label htmlFor="fd-herd">Herd</Label>
                  <Picker
                    id="fd-herd"
                    value={herd}
                    onChange={loadHerd}
                    options={herds.map((h) => ({
                      value: h.herd,
                      label: `${h.herd}${h.bom ? "" : " (no ration)"}`,
                    }))}
                    label="Herd"
                    placeholder="Start blank, or load a herd…"
                  />
                </div>
              )}
              <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
                <Label htmlFor="fd-name">{target === "ration" ? "Ration name" : "Concentrate name"}</Label>
                <Input
                  id="fd-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={target === "ration" ? "e.g. Finishing group 1" : "e.g. Finisher Pellets 14"}
                />
              </div>
            </div>

            {stranded.length > 0 && (
              <Notice tone="info">
                <span className="flex flex-wrap items-center gap-3">
                  <span>
                    This farm no longer pre-manufactures concentrate, but the recipe still uses{" "}
                    {stranded.map((s) => s.item_name).join(", ")}.
                  </span>
                  <Button variant="secondary" size="sm" onClick={() => void expand()}>
                    Expand into ingredients
                  </Button>
                </span>
              </Notice>
            )}

            <RecipeModeBar mode={mode} idPrefix="fd" per={target === "ration" ? "head per day" : "batch"} />

            <div className="flex flex-col gap-2">
              {rows.map((r, i) => (
                <div
                  key={r.key}
                  className="flex flex-wrap items-end gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]"
                >
                  <div className="flex min-w-[200px] flex-1 flex-col gap-1.5">
                    <Label htmlFor={`fd-item-${r.key}`}>Feed</Label>
                    <Picker
                      id={`fd-item-${r.key}`}
                      value={r.item_code}
                      onChange={(next) => pickFor(i, next)}
                      options={options}
                      label="Feed"
                      placeholder="Choose a feed…"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`fd-unit-${r.key}`}>Unit</Label>
                    <UnitPicker
                      id={`fd-unit-${r.key}`}
                      value={r.unit}
                      onChange={(unit) =>
                        setRows((s) => s.map((x, j) => (j === i ? { ...x, unit, pct: "" } : x)))
                      }
                    />
                  </div>
                  {mode.on && (r.unit || "kg") === "kg" ? (
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor={`fd-pct-${r.key}`}>Share (%)</Label>
                      <Input
                        id={`fd-pct-${r.key}`}
                        type="number"
                        min={0}
                        max={100}
                        step="any"
                        className="w-24 text-right tabular-nums"
                        value={r.pct ?? ""}
                        onChange={(e) => mode.changePct(r.key, e.target.value)}
                      />
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor={`fd-qty-${r.key}`}>
                        {(r.unit || "kg") === "kg" ? "Amount (kg)" : `Dose (${unitLabel(r.unit!)} a head)`}
                      </Label>
                      <Input
                        id={`fd-qty-${r.key}`}
                        type="number"
                        min={0}
                        step="any"
                        className="w-28 text-right tabular-nums"
                        value={r.qty}
                        onChange={(e) =>
                          setRows((s) => s.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))
                        }
                      />
                    </div>
                  )}
                  <span className="pb-2 text-[11.5px] tabular-nums text-[var(--sd-quiet)]">
                    {(r.unit || "kg") !== "kg"
                      ? `dose, outside the 100%${
                          target === "ration" && chosenHerd
                            ? ` · ${doseForHerd(r.qty, r.unit as "Gram" | "Millilitre", chosenHerd.heads)} for the herd`
                            : ""
                        }`
                      : mode.on
                        ? `${fmt(num(r.qty))} kg`
                        : ""}
                  </span>
                  <button
                    type="button"
                    onClick={() => setRows((s) => s.filter((_, j) => j !== i))}
                    aria-label="Take this feed out"
                    className="mb-2 text-[var(--sd-quiet)] hover:text-[var(--sd-sev-critical)]"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() => setRows((s) => [...s, { key: nextKey++, item_code: "", qty: "" }])}
                className="inline-flex w-fit items-center gap-1.5 text-[12.5px] font-medium text-[var(--sd-muted)] hover:text-[var(--sd-ink)]"
              >
                <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
                Another feed
              </button>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3 shadow-[var(--sd-shadow-inset)]">
              <span className="text-[12.5px] text-[var(--sd-muted)]">
                {target === "ration" ? "One head, one day" : "One batch"}
                {rows.some((r) => (r.unit || "kg") !== "kg") ? " · doses not included" : ""}
              </span>
              <span className="text-[15px] font-semibold tabular-nums text-[var(--sd-ink)]">
                {fmt(total)} kg
                {target === "ration" && chosenHerd && (
                  <span className="ml-2 text-[12px] font-normal text-[var(--sd-muted)]">
                    · {fmt(total * chosenHerd.heads)} kg for {chosenHerd.heads} head
                  </span>
                )}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => void save()} disabled={!canSave}>
                <Save className="mr-2 h-4 w-4" strokeWidth={1.75} />
                {busy
                  ? "Saving…"
                  : target === "ration"
                    ? chosenHerd ? `Save as the ${chosenHerd.herd} ration` : "Save as a herd ration"
                    : "Save as a concentrate"}
              </Button>
              <Button variant="secondary" onClick={() => { setRows([]); setHerd(""); setName(""); }}>
                Start blank
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Right: what is in it. */}
        <NutritionPanel
          lines={lines}
          perUnit={target === "ration" ? "head per day" : "batch"}
          className="self-start"
        />
      </div>

      <Dialog open={allOpen} onOpenChange={(o) => !allBusy && setAllOpen(o)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Manufacture all</DialogTitle>
            <DialogDescription>
              Mix the day&rsquo;s feed for every herd that is still owed some. The stores decide
              what can be covered; anything short is recorded and waits for stock.
            </DialogDescription>
          </DialogHeader>

          {!all && <Loader2 className="h-4 w-4 animate-spin" />}
          {all && !allDone && (
            <div className="flex flex-col gap-3">
              {all.concentrates.length > 0 && (
                <div>
                  <p className="text-[12.5px] font-medium">Concentrates mixed first</p>
                  <ul className="text-[13px] text-[var(--sd-muted)]">
                    {all.concentrates.map((c) => (
                      <li key={c.item_code}>
                        {c.item_name}: {fmt(c.qty)} kg
                        {c.batches ? ` (${c.batches} batch${c.batches === 1 ? "" : "es"})` : ""}
                        {c.can_manufacture === false ? " — short of ingredients" : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {all.herds.length === 0 ? (
                <p className="text-[13px] text-[var(--sd-muted)]">Every herd is already fed for today.</p>
              ) : (
                <table className="w-full border-separate border-spacing-0 text-[13px]">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--sd-quiet)]">
                      <th className="py-1 pr-4 font-medium">Herd</th>
                      <th className="py-1 pr-4 text-right font-medium">Head</th>
                      <th className="py-1 pr-4 text-right font-medium">Portion</th>
                      <th className="py-1 pr-4 text-right font-medium">
                        {typingTotals ? "Suggested (kg)" : "Mix (kg)"}
                      </th>
                      {typingTotals && <th className="py-1 pr-4 text-right font-medium">Total fed (kg)</th>}
                      <th className="py-1 pl-4 text-left font-medium">Stock</th>
                    </tr>
                  </thead>
                  <tbody>
                    {all.herds.map((h) => (
                      <tr key={h.herd} className="border-t border-[var(--sd-line)]">
                        <td className="py-1.5 pr-4 align-top">{h.herd}</td>
                        <td className="py-1.5 pr-4 text-right align-top tabular-nums">{h.heads}</td>
                        <td className="py-1.5 pr-4 text-right align-top tabular-nums">{fmt(h.portion)}</td>
                        <td className="py-1.5 pr-4 text-right align-top tabular-nums">
                          {fmt(typingTotals ? (h.suggested_qty ?? h.qty) : h.qty)}
                        </td>
                        {typingTotals && (
                          <td className="py-1 pr-4 text-right align-top">
                            <Input
                              aria-label={`Total fed to ${h.herd} (kg)`}
                              type="number"
                              min={0}
                              step="any"
                              className="ml-auto h-8 w-24 text-right tabular-nums"
                              value={allTotals[h.herd] ?? ""}
                              onChange={(e) => setAllTotals((s) => ({ ...s, [h.herd]: e.target.value }))}
                            />
                          </td>
                        )}
                        <td className="max-w-[220px] py-1.5 pl-4 align-top text-[12px] break-words">
                          {h.short?.length ? (
                            <span className="text-[var(--sd-sev-critical)]">
                              short: {h.short.map((s) => s.item_name).join(", ")}
                            </span>
                          ) : (
                            "covered"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {typingTotals && (
                <p className="text-[12px] text-[var(--sd-muted)]">
                  This farm does not feed by head count: the suggestion is head count &times; ration
                  per head ({fmt(all.herds.reduce((s, h) => s + (h.suggested_qty ?? h.qty), 0))} kg in
                  all). What you type is what is mixed; a herd left blank is not fed.
                </p>
              )}
              {all.skipped.length > 0 && (
                <p className="text-[12px] text-[var(--sd-muted)]">
                  Left out: {all.skipped.map((s) => `${s.herd} (${s.reason})`).join(", ")}.
                </p>
              )}
              <div className="flex gap-3">
                <Button onClick={() => void confirmAll()} disabled={allBusy || all.herds.length === 0}>
                  {allBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Mix them all"}
                </Button>
                <Button variant="secondary" onClick={() => setAllOpen(false)} disabled={allBusy}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
          {allDone && (
            <div className="flex flex-col gap-2">
              {allDone.concentrates.map((c) => (
                <Notice key={c.item_code} tone={c.warning ? "error" : "ok"}>
                  {c.item_name}: {c.warning ? c.warning : `mixed ${fmt(c.qty)} kg — ${c.work_order}`}
                </Notice>
              ))}
              {allDone.herds.map((h) => (
                <Notice key={h.herd} tone={h.status === "error" ? "error" : h.warnings?.length ? "info" : "ok"}>
                  {h.herd}:{" "}
                  {h.status === "error"
                    ? h.error
                    : `${h.status} — ${fmt(h.produced_qty ?? h.qty)} kg, ${h.work_order ?? ""}${
                        h.warnings?.length ? ` · ${h.warnings.join("; ")}` : ""
                      }`}
                </Notice>
              ))}
              <div>
                <Button onClick={() => setAllOpen(false)}>Close</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </Page>
  );
}
