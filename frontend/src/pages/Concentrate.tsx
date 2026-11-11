import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { Picker } from "@/components/ui/picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isError } from "@/lib/frappe";
import { canMix, concentratesInUse } from "@/lib/roles";
import { routeHash } from "@/lib/router";
import {
  concentrates,
  feedBatches,
  manufactureConcentrate,
  type BatchPlan,
  batchNote,
  type Concentrate,
} from "@/lib/feeding";
import { fmt, num } from "@/lib/utils";

/** The Ration Editor, opened on one concentrate's recipe (or a new one). */
export function concentrateRecipeHref(item: string | null): string {
  return `${routeHash("ration-editor")}?concentrate=${encodeURIComponent(item ?? "new")}`;
}

/**
 * Concentrate: where a batch for the store is MIXED, by the kilo.
 *
 * The recipe is not written here. A concentrate's recipe is written in the
 * Ration Editor, the one place any recipe is; "Recipe" and "New concentrate"
 * open it there. This window exists only on a farm that has a concentrate
 * stage at all (lib/roles: concentratesInUse) — the sidebar does not offer it
 * and the route does not open it anywhere else.
 *
 * WHAT COUNTS AS ONE is the rule the Ration Editor highlights on — a BOM line
 * that is itself manufactured, or one named bought-in on Livestock Settings.
 * Not `custom_ration_kind`: this page once decided by that stamp and listed
 * nothing while the editor highlighted five in the very same recipes.
 *
 * THE INGREDIENTS DECIDE THE WEIGHT. What the recipe makes is the sum of its
 * lines. A typed output lets 5000 kg and 6000 kg produce 100 kg of meal, which
 * nobody can check against a mixer.
 *
 * A STORE PER INGREDIENT, because silage comes from a pit and the mineral from
 * the feed store. One store for the whole run is a run that cannot be posted.
 */

const DEFAULT_BATCH = 1000;

export function Concentrate() {
  const [list, setList] = useState<Concentrate[] | null>(null);
  const [stores, setStores] = useState<string[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [mixQty, setMixQty] = useState<Record<string, string>>({});
  const [lineStore, setLineStore] = useState<Record<string, string>>({});
  const [lineBatch, setLineBatch] = useState<Record<string, string>>({});
  const [plans, setPlans] = useState<Record<string, BatchPlan>>({});
  const [to, setTo] = useState("");
  const [mixing, setMixing] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);

  const load = useCallback(
    async (qtyByItem?: Record<string, number>) => {
      const r = await concentrates(qtyByItem);
      if (isError(r)) {
        setProblem(r.error);
        setList([]);
        return;
      }
      setList(r.concentrates);
      setStores(r.warehouses || []);
      setTo((cur) => cur || r.default_target || "");
    },
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const chosen = useMemo(
    () => (list || []).find((c) => c.item_code === open) || null,
    [list, open],
  );

  const qtyFor = (c: Concentrate) => mixQty[c.item_code] ?? String(DEFAULT_BATCH);

  /** Re-price the open recipe against the stores for the tonnage typed. */
  async function reprice(c: Concentrate) {
    const q = num(qtyFor(c));
    if (q > 0) await load({ [c.item_code]: q });
  }

  /** What the rule would take for this recipe, so the page can show it and
   *  let the operator change it before anything is posted. */
  const loadPlan = useCallback(
    async (c: Concentrate) => {
      const lines = c.lines
        .map((l) => ({
          item_code: l.item_code,
          qty: l.required_qty,
          warehouse: lineStore[`${c.item_code}:${l.item_code}`] || l.source_warehouse || "",
        }))
        .filter((l) => l.warehouse);
      if (!lines.length) return;
      const r = await feedBatches(lines);
      if (isError(r)) return;
      setPlans((s) => {
        const next = { ...s };
        for (const p of r.lines) next[`${c.item_code}:${p.item_code}`] = p;
        return next;
      });
    },
    [lineStore],
  );

  useEffect(() => {
    if (chosen) void loadPlan(chosen);
  }, [chosen, loadPlan]);

  async function mix(c: Concentrate) {
    const qty = num(qtyFor(c));
    if (qty <= 0) {
      setProblem("Enter how many kilos to mix.");
      return;
    }
    if (!to) {
      setProblem("Say which store the finished mix goes into.");
      return;
    }
    const picks: Record<string, string> = {};
    const batches: Record<string, string> = {};
    for (const l of c.lines) {
      const key = `${c.item_code}:${l.item_code}`;
      if (lineStore[key]) picks[l.item_code] = lineStore[key];
      if (lineBatch[key]) batches[l.item_code] = lineBatch[key];
    }
    setMixing(c.item_code);
    setProblem(null);
    const r = await manufactureConcentrate({
      item_code: c.item_code,
      qty,
      bom_no: c.bom_no,
      target_warehouse: to,
      source_by_item: Object.keys(picks).length ? JSON.stringify(picks) : undefined,
      batch_by_item: Object.keys(batches).length ? JSON.stringify(batches) : undefined,
    });
    setMixing(null);
    if (isError(r)) {
      setProblem(r.error);
      return;
    }
    setSaid(
      `Mixed ${fmt(r.produced_qty)} ${r.uom || "kg"} of ${c.item_name} into ${to} — Work Order ${r.work_order}.`,
    );
    void load();
  }

  // A farm that mixes straight from raw ingredients has no concentrate stage.
  // The route does not open this page there (App); this is what a stale tab
  // shows rather than a mixer the server would refuse.
  if (!concentratesInUse()) {
    return (
      <Page>
        <PageHeading eyebrow="Feeding" title="Concentrate">
          Not used on this farm.
        </PageHeading>
        <Notice tone="info">
          No herd on this farm eats a pre-made concentrate: Livestock Settings &gt; Pre-manufacture
          Concentrate is off and no herd is set to Pre-manufacture on Herds. Every ration is mixed
          from raw ingredients — write it in the Ration Editor and mix it on Feeding.
        </Notice>
      </Page>
    );
  }

  return (
    <Page>
      <PageHeading
        eyebrow="Feeding"
        title="Concentrate"
        actions={
          <Button asChild variant="secondary">
            <a href={concentrateRecipeHref(null)}>New concentrate</a>
          </Button>
        }
      >
        A mix made for the store, by the batch. Not for a herd, and not for a number of days.
        Its recipe is written in the Ration Editor; it is mixed here.
      </PageHeading>

      {problem && <Notice tone="error">{problem}</Notice>}
      {said && <Notice tone="ok">{said}</Notice>}

      <FigureRow>
        <Figure loading={!list} label="Concentrates" value={String(list?.length ?? 0)} hint="the farm mixes" />
        <Figure
          loading={!list}
          label="In store"
          value={fmt((list || []).reduce((s, c) => s + c.in_store, 0))}
          hint="kg on the shelf"
        />
      </FigureRow>

      <Card>
        <CardHeader>
          <CardTitle>What the farm mixes</CardTitle>
          <CardDescription>
            Open one to see what it takes and where that stock is. Say how many kilos you want
            — every ingredient scales from the recipe — then choose where each comes from and
            where the finished mix goes.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex min-w-[240px] max-w-[460px] flex-col gap-1.5">
            <Label htmlFor="c-to">Put the finished mix in</Label>
            <Picker
              id="c-to"
              value={to}
              onChange={setTo}
              options={stores.map((w) => ({ value: w, label: w }))}
              label="Destination store"
              placeholder="Choose a store…"
            />
          </div>

          {!list ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : list.length === 0 ? (
            <p className="text-[13px] text-[var(--sd-muted)]">
              No concentrates yet. Write one with New concentrate.
            </p>
          ) : (
            list.map((c) => {
              const isOpen = open === c.item_code;
              return (
                <div
                  key={c.item_code}
                  className="flex flex-col gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]"
                >
                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <button
                      type="button"
                      className="flex flex-col items-start text-left"
                      onClick={() => setOpen(isOpen ? null : c.item_code)}
                    >
                      <span className="text-[14px] font-medium">{c.item_name}</span>
                      <span className="text-[12px] text-[var(--sd-muted)]">
                        {c.lines.length} ingredients · recipe makes {fmt(c.base_qty)}{" "}
                        {c.uom || "kg"}
                        {c.stores.length
                          ? ` · ${c.stores.map((s) => `${fmt(s.qty)} in ${s.warehouse}`).join(", ")}`
                          : " · none in store"}
                      </span>
                    </button>
                    <div className="flex items-end gap-2">
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor={`mix-${c.item_code}`}>Mix (kg)</Label>
                        <Input
                          id={`mix-${c.item_code}`}
                          type="number"
                          min="0"
                          className="w-28"
                          value={qtyFor(c)}
                          onChange={(e) =>
                            setMixQty((s) => ({ ...s, [c.item_code]: e.target.value }))
                          }
                          onBlur={() => void reprice(c)}
                        />
                      </div>
                      <Button asChild variant="secondary">
                        <a
                          href={concentrateRecipeHref(c.item_code)}
                          title="Open this recipe in the Ration Editor"
                        >
                          Recipe
                        </a>
                      </Button>
                      {canMix() && (
                        <Button disabled={mixing === c.item_code} onClick={() => void mix(c)}>
                          {mixing === c.item_code ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            "Mix"
                          )}
                        </Button>
                      )}
                    </div>
                  </div>

                  {isOpen && (
                    <div className="flex flex-col gap-2 border-t border-[var(--sd-line)] pt-3">
                      <p className="text-[12px] text-[var(--sd-quiet)]">
                        For {fmt(num(qtyFor(c)))} kg. Each line shows what is in the store it
                        would come from; change the store to draw it from somewhere else.
                      </p>
                      {c.lines.map((l) => {
                        const key = `${c.item_code}:${l.item_code}`;
                        const short = l.short_qty > 0;
                        return (
                          <div
                            key={l.item_code}
                            className="flex flex-wrap items-end gap-3 rounded-[var(--sd-radius-md,8px)] px-2 py-2"
                          >
                            <div className="flex min-w-[180px] flex-1 flex-col">
                              <span className="text-[13px] font-medium">{l.item_name}</span>
                              <span
                                className={
                                  short
                                    ? "text-[12px] text-[var(--sd-danger,#dc2626)]"
                                    : "text-[12px] text-[var(--sd-muted)]"
                                }
                              >
                                needs {fmt(l.required_qty)} {l.uom} · {fmt(l.available)} here
                                {l.available_elsewhere > 0
                                  ? ` · ${fmt(l.available_elsewhere)} elsewhere`
                                  : ""}
                                {short ? ` · short ${fmt(l.short_qty)}` : ""}
                              </span>
                            </div>
                            <div className="flex min-w-[240px] flex-col gap-1.5">
                              <Label htmlFor={`w-${key}`}>Take from</Label>
                              <Picker
                                id={`w-${key}`}
                                value={lineStore[key] ?? ""}
                                onChange={(next) =>
                                  setLineStore((s) => ({ ...s, [key]: next }))
                                }
                                options={[
                                  {
                                    value: "",
                                    label: l.source_warehouse
                                      ? `${l.source_warehouse} (chosen)`
                                      : "As chosen",
                                  },
                                  ...stores.map((w) => ({ value: w, label: w })),
                                ]}
                                label="Source store"
                                placeholder="As chosen"
                              />
                            </div>
                            <div className="flex min-w-[240px] flex-col gap-1.5">
                              <Label htmlFor={`b-${key}`}>Batch</Label>
                              <Picker
                                id={`b-${key}`}
                                value={lineBatch[key] ?? ""}
                                onChange={(next) =>
                                  setLineBatch((s) => ({ ...s, [key]: next }))
                                }
                                options={[
                                  {
                                    value: "",
                                    label: batchNote(plans[key]),
                                  },
                                  ...(plans[key]?.available ?? []).map((b) => ({
                                    value: b.batch_no,
                                    label: `${b.batch_no} · ${fmt(b.qty)} here${
                                      b.expiry_date ? ` · expires ${b.expiry_date}` : ""
                                    }`,
                                  })),
                                ]}
                                label="Batch"
                                placeholder="Chosen by the rule"
                              />
                              {/* The proposal, shown as text rather than as the
                                  picker's empty option — Picker drops an option
                                  with an empty value, so a rule nobody can see
                                  would be exactly the problem this page exists
                                  to fix. */}
                              <span
                                className={
                                  plans[key] && !plans[key].picks.length
                                    ? "text-[11px] text-[var(--sd-danger,#dc2626)]"
                                    : "text-[11px] text-[var(--sd-quiet)]"
                                }
                              >
                                {lineBatch[key] ? "Chosen by you" : batchNote(plans[key])}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
