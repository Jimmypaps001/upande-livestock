import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Search } from "lucide-react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { isError } from "@/lib/frappe";
import {
  ALL_WAREHOUSES,
  feedInStore,
  groupStock,
  totalsByUom,
  type StoreItem,
} from "@/lib/stock";
import { fmt } from "@/lib/utils";

/**
 * What the feed stores hold.
 *
 * One row per item PER WAREHOUSE, as the endpoint returns it — deliberately
 * not summed. The same ingredient sits in more than one store here, and a
 * single total hides the store that is empty, which is the one that stops a
 * run.
 *
 * Concentrates and raw ingredients are listed apart because they are restocked
 * differently: a raw ingredient is bought, a concentrate is mixed (see the
 * Concentrate page for the batches that would do it).
 *
 * Quantities are shown in the unit the store counts in. Nothing on this page
 * converts a unit — hay is written in kg on a recipe but stocked in BALE, and
 * this page is the store's view, not the recipe's.
 */

function StockTable({ items, empty }: { items: StoreItem[]; empty: string }) {
  if (!items.length)
    return (
      <div className="rounded-[var(--sd-radius-lg)] border border-dashed border-[var(--sd-line)] px-4 py-6 text-center text-[13px] text-[var(--sd-quiet)]">
        {empty}
      </div>
    );
  return (
    <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
      <table className="w-full min-w-[40rem] text-[13px]">
        <thead>
          <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
            <th className="px-3 py-2.5 font-medium">Item</th>
            <th className="px-3 py-2.5 font-medium">Store</th>
            <th className="px-3 py-2.5 text-right font-medium">Quantity</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr
              key={`${it.item_code}::${it.warehouse}`}
              className="border-b border-[var(--sd-line-soft)] last:border-0"
            >
              <td className="px-3 py-2.5 font-medium text-[var(--sd-ink)]">
                {it.item_name || it.item_code}
                <div className="text-[11px] font-normal text-[var(--sd-quiet)]">
                  {it.item_code}
                </div>
              </td>
              <td className="px-3 py-2.5 text-[var(--sd-muted)]">{it.warehouse}</td>
              <td
                className={
                  "px-3 py-2.5 text-right tabular-nums " +
                  (Number(it.qty) > 0 ? "" : "text-[var(--sd-sev-critical)]")
                }
              >
                {fmt(it.qty)}{" "}
                <span className="text-[11px] text-[var(--sd-quiet)]">{it.uom}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Totals({ label, items }: { label: string; items: StoreItem[] }) {
  const totals = totalsByUom(items);
  if (!totals.length) return null;
  return (
    <p className="text-[12px] text-[var(--sd-quiet)]">
      {label}: {totals.map((t) => `${fmt(t.qty)} ${t.uom}`).join(" · ")}
    </p>
  );
}

export function Stock() {
  const [warehouse, setWarehouse] = useState<string>(ALL_WAREHOUSES);
  const [warehouses, setWarehouses] = useState<string[]>([]);
  const [items, setItems] = useState<StoreItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [term, setTerm] = useState("");

  const load = useCallback(async (wh: string) => {
    setLoading(true);
    const r = await feedInStore(wh);
    setLoading(false);
    if (isError(r)) {
      setItems([]);
      setError(r.error);
      return;
    }
    setError(null);
    setItems(r.items || []);
    // The warehouse list comes back whole even when one store is asked for, so
    // filtering never strips the picker down to the store already chosen.
    if (r.warehouses?.length) setWarehouses(r.warehouses);
  }, []);

  useEffect(() => {
    load(warehouse);
  }, [load, warehouse]);

  const filtered = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (it) =>
        (it.item_name || "").toLowerCase().includes(q) ||
        (it.item_code || "").toLowerCase().includes(q) ||
        (it.warehouse || "").toLowerCase().includes(q),
    );
  }, [items, term]);

  const { rations, concentrates, ingredients } = groupStock(filtered);

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Feeding" title="Feed in store">
        What the farm is actually holding — raw ingredients and mixed concentrate, in the
        unit each store counts in. A line is listed once per store, not summed across
        them, because the store that is empty is the one that stops a run.
      </PageHeading>

      {error && <Notice tone="error">{error}</Notice>}

      <Card>
        <CardHeader className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <CardTitle>Stores</CardTitle>
            <CardDescription>
              Every warehouse the feed items sit in, in the order Livestock Settings names
              them.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex w-full max-w-[24rem] flex-col gap-1.5">
              <Label htmlFor="stock-wh" className="text-[var(--sd-muted)]">
                Store
              </Label>
              <Select value={warehouse} onValueChange={setWarehouse}>
                <SelectTrigger id="stock-wh">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_WAREHOUSES}>Every store</SelectItem>
                  {warehouses.map((w) => (
                    <SelectItem key={w} value={w}>
                      {w}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex w-full max-w-[20rem] flex-col gap-1.5">
              <Label htmlFor="stock-q" className="text-[var(--sd-muted)]">
                Find an item
              </Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--sd-quiet)]" />
                <Input
                  id="stock-q"
                  className="pl-8"
                  placeholder="Name, code or store…"
                  value={term}
                  onChange={(e) => setTerm(e.target.value)}
                />
              </div>
            </div>
            <Button variant="outline" onClick={() => load(warehouse)} disabled={loading}>
              {loading ? "Reading the stores…" : "Refresh"}
            </Button>
            {loading && <Loader2 className="h-4 w-4 animate-spin text-[var(--sd-quiet)]" />}
          </div>
        </CardHeader>
        <CardContent>
          <FigureRow>
            <Figure
              label="Ingredient lines"
              value={String(ingredients.length)}
              hint="item × store"
            />
            <Figure
              label="Concentrate lines"
              value={String(concentrates.length)}
              hint="item × store"
            />
            <Figure
              label="Mixed ration lines"
              value={String(rations.length)}
              hint="TMR already made"
            />
            <Figure
              label="Stores holding feed"
              value={String(new Set(filtered.map((i) => i.warehouse)).size)}
            />
          </FigureRow>
        </CardContent>
      </Card>

      {rations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Mixed ration</CardTitle>
            <CardDescription>
              Finished TMR sitting in a store, already mixed and waiting for a trough.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <StockTable items={rations} empty="No mixed ration in these stores." />
            <Totals label="Held" items={rations} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Concentrate</CardTitle>
          <CardDescription>
            Mixed feed held ready. What it would take to mix more is on the Concentrate
            page.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <StockTable
            items={concentrates}
            empty={loading ? "Reading the stores…" : "No concentrate in these stores."}
          />
          <Totals label="Held" items={concentrates} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Feed and ingredients</CardTitle>
          <CardDescription>
            Raw materials — silage, hay, the bought-in straights a concentrate is mixed
            from.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <StockTable
            items={ingredients}
            empty={loading ? "Reading the stores…" : "No feed ingredients in these stores."}
          />
          <Totals label="Held" items={ingredients} />
        </CardContent>
      </Card>
    </Page>
  );
}
