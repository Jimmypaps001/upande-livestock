import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { DayStatus } from "@/components/feeding/DayStatus";
import { ManualConfig } from "@/components/feeding/ManualConfig";
import { Mark, Notice, Pill } from "@/components/feeding/Notice";
import { PortionSwitch } from "@/components/feeding/PortionSwitch";
import { PostingDate } from "@/components/feeding/PostingDate";
import { RecipePicker, recipeLabel } from "@/components/feeding/RecipePicker";
import { RequirementTable } from "@/components/feeding/RequirementTable";
import { Figure, FigureRow } from "@/components/Figure";
import { Page, PageHeading } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isError } from "@/lib/frappe";
import {
  feedDayStatus,
  feedOptions,
  feedingProgram,
  herdRecipes,
  manualFeed,
  manualRowsDirty,
  manufactureFeed,
  runKg,
  runRationQty,
  seedRowsFromRecipe,
  type FeedDayStatus,
  type FeedingProgram,
  type HerdOption,
  type ManualRow,
  type Recipe,
} from "@/lib/feeding";
import { fmt, num, todayISO } from "@/lib/utils";

export function Feeding() {
  const [herds, setHerds] = useState<HerdOption[]>([]);
  const [herd, setHerd] = useState("");
  const [program, setProgram] = useState<FeedingProgram | null>(null);
  const [day, setDay] = useState<FeedDayStatus | null>(null);
  const [loading, setLoading] = useState(false);
  /** Whatever the server last said. Never reworded — see components/feeding/Notice. */
  const [failure, setFailure] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lastRunMode, setLastRunMode] = useState<string | null>(null);

  /**
   * The day this page posts against — one decision, at the top, for both tabs.
   *
   * It used to be two separate controls buried in the two forms, which meant
   * the operator could set the system tab to a past day and leave the manual
   * tab on today without either screen saying so. There is one date now, and
   * the switch above it says which mode the whole page is in.
   */
  const [backdating, setBackdating] = useState(false);
  const [postDate, setPostDate] = useState(todayISO());

  // System tab
  const [portion, setPortion] = useState(0.5);
  const [mixing, setMixing] = useState(false);

  // Manual tab — seeded once per herd (and once per recipe pick), then the
  // operator's edits are left alone: re-seeding on every refresh would wipe a
  // half-typed recipe under their fingers.
  const [manualRows, setManualRows] = useState<ManualRow[] | null>(null);
  const [manualSeed, setManualSeed] = useState<ManualRow[] | null>(null);
  const [manualHerd, setManualHerd] = useState<string | null>(null);
  const [manualHeads, setManualHeads] = useState("");
  const [manualBusy, setManualBusy] = useState(false);

  // The recipe picker, shared by both tabs so a choice on one is the same
  // choice on the other. `standingBom` is the herd's normal ration —
  // `herd_recipes`' default — and `selectedBom` is whichever recipe (standing
  // or previously tuned) is currently in play.
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [standingBom, setStandingBom] = useState("");
  const [selectedBom, setSelectedBom] = useState("");

  useEffect(() => {
    feedOptions().then((r) => {
      if (isError(r)) {
        setFailure(r.error);
        return;
      }
      setHerds(r.herds || []);
    });
  }, []);

  const load = useCallback(
    async (name: string, seedManual: boolean) => {
      if (!name) {
        setProgram(null);
        setDay(null);
        setRecipes([]);
        setStandingBom("");
        return;
      }
      setLoading(true);
      setFailure(null);
      // The day's state travels with the programme: the farm feeds twice, so
      // "what does this herd need" is not the question at the trough. The
      // recipe list travels with it too — both tabs' pickers read from the
      // same fetch, so there is never a second round trip to seed the manual
      // tab's rows once a recipe is chosen.
      const [p, d, rec] = await Promise.all([
        feedingProgram(name),
        feedDayStatus(name),
        herdRecipes(name),
      ]);
      setLoading(false);
      if (isError(p)) {
        setProgram(null);
        setDay(null);
        setFailure(p.error);
        return;
      }
      setProgram(p);
      const dayStatus = isError(d) ? null : d;
      setDay(dayStatus);
      // The suggested portion is snapped to the nearer of the two the switch
      // offers: the server may answer 0.37 for a herd already part-fed, and
      // this screen never shows a decimal.
      const suggested = dayStatus?.suggested_portion ?? 1;
      setPortion(suggested > 0 && suggested <= 0.5 ? 0.5 : 1);

      // The recipe list refreshes on every load (e.g. a fresh tune just
      // minted shows up next time), but only a herd switch — never a mere
      // refresh after a run — resets which recipe is selected and re-seeds
      // the manual rows. That reset is unconditional here because it is a
      // different herd: there is nothing from the previous herd worth
      // protecting.
      if (isError(rec)) {
        setRecipes([]);
        setStandingBom("");
        if (seedManual) {
          setSelectedBom("");
          setManualRows(null);
          setManualSeed(null);
          setManualHerd(p.herd);
          setManualHeads(String(p.heads || ""));
        }
        return;
      }
      setRecipes(rec.recipes || []);
      setStandingBom(rec.standing_bom);
      if (seedManual) {
        const standing =
          rec.recipes.find((r) => r.bom_no === rec.standing_bom) || rec.recipes[0];
        setSelectedBom(rec.standing_bom);
        const seeded = standing ? seedRowsFromRecipe(standing) : [];
        setManualRows(seeded);
        setManualSeed(seeded);
        setManualHerd(p.herd);
        setManualHeads(String(p.heads || ""));
      }
    },
    [],
  );

  function chooseHerd(name: string) {
    setHerd(name);
    setSuccess(null);
    setLastRunMode(null);
    load(name, true);
  }

  /** Live mode always posts today, whatever the field last held. */
  const effectiveDate = backdating ? postDate : todayISO();

  const selectedRecipe = recipes.find((r) => r.bom_no === selectedBom) || null;
  const usingStandingRecipe = !selectedBom || selectedBom === standingBom;

  /**
   * The picker's onChange, shared by both tabs.
   *
   * Re-seeding is silent when the manual rows still match what was last
   * seeded — there is nothing to lose. Once the operator has typed something
   * different, switching recipes asks first: this moves real stock, and a
   * hand-tuned quantity discarded without warning is exactly the mistake the
   * confirm is here to catch. Cancelling leaves the selection and the rows
   * exactly as they were.
   */
  function chooseRecipe(bomNo: string) {
    if (bomNo === selectedBom) return;
    const recipe = recipes.find((r) => r.bom_no === bomNo);
    if (!recipe) return;
    if (manualRowsDirty(manualRows, manualSeed)) {
      const ok = window.confirm(
        `Switching to "${recipeLabel(recipe)}" replaces the quantities you've entered with that ` +
          "recipe's own amounts. Continue?",
      );
      if (!ok) return;
    }
    setSelectedBom(bomNo);
    const seeded = seedRowsFromRecipe(recipe);
    setManualRows(seeded);
    setManualSeed(seeded);
  }

  async function mixAndFeed() {
    if (!program) return;
    setMixing(true);
    setFailure(null);
    setSuccess(null);
    // The System tab always runs through manufactureFeed, standing ration or
    // a previously-used recipe alike — bom_no carries the picker's choice,
    // and manufacture_feed.py validates it against the herd. No hand-tuning
    // happens on this tab, so nothing here ever goes through manualFeed.
    const r = await manufactureFeed({
      herd: program.herd,
      portion,
      posting_date: effectiveDate,
      bom_no: selectedBom || undefined,
    });
    setMixing(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    const recipeNote =
      !usingStandingRecipe && selectedRecipe ? ` using ${selectedRecipe.item_name}` : "";
    setSuccess(
      `Manufactured and issued ${fmt(r.produced_qty)} ${r.uom || ""} to ${
        program.herd_label || program.herd
      }${recipeNote} — Work Order ${r.work_order}, issued on ${r.issue_stock_entry}.`,
    );
    setLastRunMode(effectiveDate !== todayISO() ? "Backdated" : null);
    load(program.herd, false);
  }

  async function submitManual() {
    if (!program) return;
    const heads = num(manualHeads);
    const lines = (manualRows || [])
      .map((r) => ({ item_code: r.item_code, qty: num(r.qty) }))
      .filter((l) => l.qty > 0);
    setFailure(null);
    setSuccess(null);
    if (heads <= 0) {
      setFailure("Enter how many animals were fed.");
      return;
    }
    if (!lines.length) {
      setFailure("Enter a quantity for at least one ingredient.");
      return;
    }
    setManualBusy(true);
    // The chosen recipe is the base the tune descends from — never always
    // the herd's standing ration — so a tune made from a previously-used
    // recipe stays a descendant of what the operator was actually looking
    // at, not of a ration they may have since moved away from.
    const r = await manualFeed({
      herd: program.herd,
      lines,
      heads,
      posting_date: effectiveDate,
      base_bom: selectedBom || undefined,
    });
    setManualBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setSuccess(
      `Manufactured and issued ${fmt(r.produced_qty)} ${r.uom || ""} — Work Order ${
        r.work_order
      }, issued on ${r.issue_stock_entry}.`,
    );
    setLastRunMode(effectiveDate !== todayISO() ? "Manual · Backdated" : "Manual");
    // Reseed from the fresh programme (and the possibly-just-minted recipe
    // list) next time this herd is chosen.
    setManualHerd(null);
    load(program.herd, false);
  }

  // Both follow the recipe picker, not just the standing programme — see
  // runKg/runRationQty's docstrings for why the standing ration still reads
  // off the day/programme figures while a previously-used or tuned pick
  // recomputes from its own per-head amount.
  const kg = runKg(day, portion, selectedRecipe, program?.heads);
  const rationQty = runRationQty(program, portion, selectedRecipe);
  const manualDisabled = !program ? "Select a herd first." : null;

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Feeding" title="Feeding">
        Pick a herd. The ration scales with head count, every line is checked against the
        feed stores first, and the whole batch is issued to that herd in the same action.
      </PageHeading>

      {/* The day this page posts against, decided before anything is filled in. */}
      <PostingDate
        backdating={backdating}
        onBackdatingChange={setBackdating}
        date={postDate}
        onDateChange={setPostDate}
        idPrefix="feed"
      />

      {failure && <Notice tone="error">{failure}</Notice>}
      {success && (
        <Notice tone="ok">
          <div className="flex flex-wrap items-center gap-2">
            <span>{success}</span>
            {lastRunMode && <Mark>{lastRunMode}</Mark>}
          </div>
        </Notice>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Herd</CardTitle>
          <CardDescription>
            Only herds with a ration BOM can be fed from here.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <div className="flex w-full max-w-sm flex-col gap-1.5">
            <Label htmlFor="feed-herd" className="text-[var(--sd-muted)]">
              Herd
            </Label>
            <Select value={herd} onValueChange={chooseHerd}>
              <SelectTrigger id="feed-herd">
                <SelectValue placeholder="Select herd…" />
              </SelectTrigger>
              <SelectContent>
                {herds.map((h) => (
                  <SelectItem key={h.name} value={h.name}>
                    {h.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {loading && (
            <div className="flex items-center gap-2 text-[13px] text-[var(--sd-muted)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              Checking the stores…
            </div>
          )}

          {program && (
            <Tabs defaultValue="system" className="flex flex-col gap-5">
              <TabsList className="self-start">
                <TabsTrigger value="system">System</TabsTrigger>
                <TabsTrigger value="manual">Manual configuration</TabsTrigger>
              </TabsList>

              <TabsContent value="system" className="flex flex-col gap-5">
                <RecipePicker
                  recipes={recipes}
                  value={selectedBom}
                  onChange={chooseRecipe}
                  idPrefix="feed-system"
                />

                <FigureRow>
                  <Figure label="Head count" value={String(program.heads)} />
                  <Figure
                    label="Per head"
                    value={fmt(program.per_head_qty)}
                    unit={program.uom}
                  />
                  <Figure
                    label="To manufacture"
                    value={fmt(program.total_manufacture_qty)}
                    unit={program.uom}
                  />
                  <Figure
                    label={`${program.production_item_name} in store`}
                    value={fmt(program.available_in_store)}
                    unit={program.uom}
                  />
                </FigureRow>

                {program.can_manufacture ? (
                  <Pill tone="ok">
                    Enough stock to manufacture {program.production_item_name}
                  </Pill>
                ) : (
                  <Pill tone="short">
                    Short: {program.shortages.map((l) => l.item_name).join(", ")}
                  </Pill>
                )}

                <RequirementTable lines={program.lines} showConcentrateTag />

                <p className="text-[12px] text-[var(--sd-quiet)]">
                  Stock is checked in the order set on Livestock Settings → Feed Source
                  Warehouses. A line is sourced from the first store that can cover it in
                  full. What each concentrate would take to mix is on the Concentrate
                  page.
                  {!usingStandingRecipe && (
                    <>
                      {" "}
                      The figures above are the standing ration's — this run will mix the
                      recipe selected above instead, and the store is still checked when it
                      posts.
                    </>
                  )}
                </p>

                <DayStatus day={day} />

                <div className="flex flex-col gap-4 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] px-4 py-4">
                  <div className="flex flex-wrap items-end justify-between gap-5">
                    <div className="flex w-full max-w-xs flex-col gap-2">
                      <Label className="text-[var(--sd-muted)]">This run</Label>
                      <PortionSwitch portion={portion} onChange={setPortion} />
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
                        Goes in the trough
                      </span>
                      <span className="text-[26px] font-semibold leading-none tracking-[-0.02em] text-[var(--sd-ink)] tabular-nums">
                        {kg == null ? "—" : fmt(kg)}
                        <span className="ml-1 text-[13px] font-medium text-[var(--sd-muted)]">
                          kg
                        </span>
                      </span>
                      {rationQty != null && (
                        <span className="text-[11px] text-[var(--sd-quiet)]">
                          {fmt(rationQty)}{" "}
                          {selectedRecipe && !selectedRecipe.is_standing
                            ? selectedRecipe.uom
                            : program.uom}{" "}
                          of {program.production_item_name}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-3">
                    <Button
                      onClick={mixAndFeed}
                      disabled={mixing || (usingStandingRecipe && !program.can_manufacture)}
                    >
                      {mixing ? "Mixing…" : "Mix & feed"}
                    </Button>
                    {effectiveDate !== todayISO() && <Mark>Backdated · {effectiveDate}</Mark>}
                    {usingStandingRecipe && !program.can_manufacture && (
                      <span className="text-[12px] text-[var(--sd-quiet)]">
                        A short line has to be covered before this run can post.
                      </span>
                    )}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="manual" className="flex flex-col gap-5">
                <RecipePicker
                  recipes={recipes}
                  value={selectedBom}
                  onChange={chooseRecipe}
                  idPrefix="feed-manual"
                />
                <ManualConfig
                  rows={manualHerd === program.herd ? manualRows : null}
                  onRowsChange={setManualRows}
                  heads={manualHeads}
                  onHeadsChange={setManualHeads}
                  date={effectiveDate}
                  onSubmit={submitManual}
                  busy={manualBusy}
                  disabledReason={manualDisabled}
                />
              </TabsContent>
            </Tabs>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
