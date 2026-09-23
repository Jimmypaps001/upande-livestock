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
 * This page used to ask `concentrate_plan(days)` how many batches to mix to
 * cover N days for the herds that eat it. That was the wrong shape for the
 * question — a mixer takes a tonne of ingredients and makes a tonne of meal
 * whether there are forty cows in the shed or none. Head count belongs to the
 * TMR, which is fed per head. Here there is no herd and no calendar.
 *
 * Three things: make one, change one, mix one.
 *
 * THE BASE IS WHAT THE LINES MAKE, declared rather than summed. 500 kg of meal
 * can come from ingredients that do not add to 500 — moisture, or a recipe
 * written in round numbers the mixer operator works to. Mixing 1000 off a 500
 * base consumes exactly twice the lines, which is ERPNext's own Work Order
 * scaling rather than arithmetic this page does.
 */

type Row = { key: number; item_code: string; qty: string };
let nextKey = 1;

export function Concentrate() {
  const [list, setList] = useState<Concentrate[] | null>(null);
  const [feeds, setFeeds] = useState<FeedChoice[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [base, setBase] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [mixQty, setMixQty] = useState<Record<string, string>>({});
  const [stores, setStores] = useState<string[]>([]);
  // Blank means "as before": every feed store searched, the WIP store for the
  // finished mix. Naming one narrows it — see _engine._source_warehouses.
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [mixing, setMixing] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await concentrates();
    if (isError(r)) {
      setProblem(r.error);
      setList([]);
      return;
    }
    setList(r.concentrates);
    setStores(r.warehouses || []);
    setTo((cur) => cur || r.default_target || "");
  }, []);

  useEffect(() => {
    void load();
    void (async () => {
      const r = await getHerdRations();
      if (!isError(r)) setFeeds(r.feeds);
    })();
  }, [load]);

  const chosen = useMemo(
    () => (list || []).find((c) => c.item_code === picked) || null,
    [list, picked],
  );

  // Editing seeds from the recipe as it stands, so saving an untouched form is
  // a no-op the server recognises rather than a new revision of the same thing.
  useEffect(() => {
    if (!chosen) return;
    setName(chosen.item_name);
    setBase(String(chosen.base_qty));
    setRows(
      chosen.lines.map((l) => ({ key: nextKey++, item_code: l.item_code, qty: String(l.qty) })),
    );
  }, [chosen?.item_code, chosen?.bom_no]);

  function startNew() {
    setPicked(null);
    setName("");
    setBase("");
    setRows([{ key: nextKey++, item_code: "", qty: "" }]);
    setSaid(null);
    setProblem(null);
  }

  const linesTotal = rows.reduce((s, r) => s + (Number(r.qty) || 0), 0);
  const ready = !!name.trim() && num(base) > 0 && rows.some((r) => r.item_code && num(r.qty) > 0);

  async function save() {
    setBusy(true);
    setProblem(null);
    const r = await setConcentrate({
      name: name.trim(),
      base_qty: num(base),
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
        ? `${r.item} now makes ${fmt(r.base_qty)} kg from these ingredients — recipe ${r.bom}.`
        : `Nothing changed — ${r.item} already says exactly this.`,
    );
    setPicked(r.item);
    void load();
  }

  async function mix(c: Concentrate) {
    const qty = num(mixQty[c.item_code] ?? String(c.base_qty));
    if (qty <= 0) {
      setProblem("Enter how many kilos to mix.");
      return;
    }
    setMixing(c.item_code);
    setProblem(null);
    const r = await manufactureConcentrate({
      item_code: c.item_code,
      qty,
      bom_no: c.bom_no,
      source_warehouse: from || undefined,
      target_warehouse: to || undefined,
    });
    setMixing(null);
    if (isError(r)) {
      setProblem(r.error);
      return;
    }
    setSaid(`Mixed ${fmt(r.produced_qty)} ${r.uom || "kg"} of ${c.item_name} — Work Order ${r.work_order}.`);
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
        <Figure loading={!list} label="Concentrates" value={String(list?.length ?? 0)} hint="recipes the farm mixes" />
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
            Pick one to change its recipe, or mix a batch of it. Type the kilos you want —
            the ingredients scale from what the recipe says they make.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-3">
            <div className="flex min-w-[240px] flex-1 flex-col gap-1.5">
              <Label htmlFor="c-from">Take ingredients from</Label>
              <Picker
                id="c-from"
                value={from}
                onChange={setFrom}
                options={[
                  { value: "", label: "Any feed store" },
                  ...stores.map((w) => ({ value: w, label: w })),
                ]}
                label="Source store"
                placeholder="Any feed store"
              />
            </div>
            <div className="flex min-w-[240px] flex-1 flex-col gap-1.5">
              <Label htmlFor="c-to">Put the mix in</Label>
              <Picker
                id="c-to"
                value={to}
                onChange={setTo}
                options={stores.map((w) => ({ value: w, label: w }))}
                label="Destination store"
                placeholder="Choose a store…"
              />
            </div>
          </div>

          {!list ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : list.length === 0 ? (
            <p className="text-[13px] text-[var(--sd-muted)]">
              No concentrates yet. Make one below.
            </p>
          ) : (
            list.map((c) => (
              <div
                key={c.item_code}
                className="flex flex-wrap items-end justify-between gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]"
              >
                <button
                  type="button"
                  className="flex flex-col items-start text-left"
                  onClick={() => setPicked(c.item_code)}
                >
                  <span className="text-[14px] font-medium">{c.item_name}</span>
                  <span className="text-[12px] text-[var(--sd-muted)]">
                    {c.lines.length} ingredients make {fmt(c.base_qty)} {c.uom || "kg"} ·{" "}
                    {fmt(c.in_store)} in store
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
                      value={mixQty[c.item_code] ?? String(c.base_qty)}
                      onChange={(e) =>
                        setMixQty((s) => ({ ...s, [c.item_code]: e.target.value }))
                      }
                    />
                  </div>
                  <Button disabled={mixing === c.item_code} onClick={() => void mix(c)}>
                    {mixing === c.item_code ? <Loader2 className="h-4 w-4 animate-spin" /> : "Mix"}
                  </Button>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{chosen ? chosen.item_name : "New concentrate"}</CardTitle>
          <CardDescription>
            {chosen
              ? `Recipe ${chosen.bom_no}. Changing it makes a new recipe; the old one stays as history.`
              : "Name it, list what goes in, and say how much that makes."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-3">
            <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
              <Label htmlFor="c-name">Name</Label>
              <Input
                id="c-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Dairy Meal 18"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="c-base">These ingredients make (kg)</Label>
              <Input
                id="c-base"
                type="number"
                min="0"
                className="w-44"
                value={base}
                onChange={(e) => setBase(e.target.value)}
                placeholder="500"
              />
            </div>
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
                <Button
                  variant="ghost"
                  onClick={() => setRows((s) => s.filter((_, j) => j !== i))}
                >
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
                {fmt(linesTotal)} kg of ingredients
                {num(base) > 0 ? ` · makes ${fmt(num(base))} kg` : ""}
              </span>
            </div>
          </div>

          <div className="flex gap-3">
            <Button disabled={!ready || busy} onClick={() => void save()}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : chosen ? "Save recipe" : "Create"}
            </Button>
            <Button variant="secondary" onClick={startNew}>
              New concentrate
            </Button>
          </div>
        </CardContent>
      </Card>
    </Page>
  );
}
