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
import { concentrates, manufactureConcentrate, setConcentrate, type Concentrate } from "@/lib/feeding";
import { getHerdRations, type FeedChoice } from "@/lib/herds";
import { fmt, num } from "@/lib/utils";

/**
 * Concentrate: a recipe for the store, mixed by the kilo.
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

type Row = { key: number; item_code: string; qty: string };
let nextKey = 1;

export function Concentrate() {
  const [list, setList] = useState<Concentrate[] | null>(null);
  const [feeds, setFeeds] = useState<FeedChoice[]>([]);
  const [stores, setStores] = useState<string[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [mixQty, setMixQty] = useState<Record<string, string>>({});
  const [lineStore, setLineStore] = useState<Record<string, string>>({});
  const [to, setTo] = useState("");
  const [mixing, setMixing] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);

  // Editing / creating
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);

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
    void (async () => {
      const r = await getHerdRations();
      if (!isError(r)) setFeeds(r.feeds);
    })();
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

  function edit(c: Concentrate) {
    setEditing(true);
    setName(c.item_name);
    setRows(c.lines.map((l) => ({ key: nextKey++, item_code: l.item_code, qty: String(l.recipe_qty) })));
  }

  function startNew() {
    setEditing(true);
    setOpen(null);
    setName("");
    setRows([{ key: nextKey++, item_code: "", qty: "" }]);
    setSaid(null);
    setProblem(null);
  }

  const total = rows.reduce((s, r) => s + (Number(r.qty) || 0), 0);
  const ready = !!name.trim() && rows.some((r) => r.item_code && num(r.qty) > 0);

  async function save() {
    setBusy(true);
    setProblem(null);
    const r = await setConcentrate({
      name: name.trim(),
      lines: rows
        .filter((x) => x.item_code && Number(x.qty) > 0)
        .map((x) => ({ item_code: x.item_code, qty: Number(x.qty) })),
    });
    setBusy(false);
    if (isError(r)) {
      setProblem(r.error);
      return;
    }
    setSaid(
      r.changed
        ? `${r.item} makes ${fmt(r.base_qty)} kg from these ingredients — recipe ${r.bom}.`
        : `Nothing changed — ${r.item} already says exactly this.`,
    );
    setEditing(false);
    setOpen(r.item);
    void load();
  }

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
    for (const l of c.lines) {
      const w = lineStore[`${c.item_code}:${l.item_code}`];
      if (w) picks[l.item_code] = w;
    }
    setMixing(c.item_code);
    setProblem(null);
    const r = await manufactureConcentrate({
      item_code: c.item_code,
      qty,
      bom_no: c.bom_no,
      target_warehouse: to,
      source_by_item: Object.keys(picks).length ? JSON.stringify(picks) : undefined,
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

  return (
    <Page>
      <PageHeading eyebrow="Feeding" title="Concentrate">
        A mix made for the store. Not for a herd, and not for a number of days.
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
              No concentrates yet. Make one below.
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
                      <Button variant="secondary" onClick={() => edit(c)}>
                        Recipe
                      </Button>
                      <Button disabled={mixing === c.item_code} onClick={() => void mix(c)}>
                        {mixing === c.item_code ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          "Mix"
                        )}
                      </Button>
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

      {editing && (
        <Card>
          <CardHeader>
            <CardTitle>{name || "New concentrate"}</CardTitle>
            <CardDescription>
              Name it and list what goes in. What the ingredients weigh is what the recipe
              makes — mixing more than that scales every line.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex min-w-[240px] max-w-[460px] flex-col gap-1.5">
              <Label htmlFor="c-name">Name</Label>
              <Input
                id="c-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Dairy Meal 18"
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label>What goes in</Label>
              {rows.map((r, i) => (
                <div
                  key={r.key}
                  className="flex flex-wrap items-end gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]"
                >
                  <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
                    <Label htmlFor={`c-item-${r.key}`}>Ingredient</Label>
                    <Picker
                      id={`c-item-${r.key}`}
                      value={r.item_code}
                      onChange={(next) =>
                        setRows((s) => s.map((x, j) => (j === i ? { ...x, item_code: next } : x)))
                      }
                      options={feeds.map((f) => ({ value: f.value, label: f.label }))}
                      label="Ingredient"
                      placeholder="Choose an ingredient…"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`c-qty-${r.key}`}>Amount (kg)</Label>
                    <Input
                      id={`c-qty-${r.key}`}
                      type="number"
                      min="0"
                      className="w-32"
                      value={r.qty}
                      onChange={(e) =>
                        setRows((s) => s.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))
                      }
                    />
                  </div>
                  <Button variant="ghost" onClick={() => setRows((s) => s.filter((_, j) => j !== i))}>
                    Remove
                  </Button>
                </div>
              ))}
              <div className="flex items-center gap-3">
                <Button
                  variant="secondary"
                  onClick={() => setRows((s) => [...s, { key: nextKey++, item_code: "", qty: "" }])}
                >
                  Add an ingredient
                </Button>
                <span className="text-[12px] text-[var(--sd-muted)]">
                  makes {fmt(total)} kg
                </span>
              </div>
            </div>

            <div className="flex gap-3">
              <Button disabled={!ready || busy} onClick={() => void save()}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save recipe"}
              </Button>
              <Button variant="secondary" onClick={() => setEditing(false)}>
                Close
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {!editing && (
        <Button variant="secondary" className="self-start" onClick={startNew}>
          New concentrate
        </Button>
      )}
    </Page>
  );
}
