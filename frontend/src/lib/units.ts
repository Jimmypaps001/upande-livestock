import { useEffect, useMemo, useState } from "react";
import { call, isError, type Envelope } from "@/lib/frappe";

/**
 * The units a feed line may be written in, and what one of each weighs.
 *
 * The stores count some feeds in other units — molasses in Litre, hay in
 * bales — so a recipe or feeding line may be written in the item's stock unit
 * or any unit in its UOM conversion table, with the kilo equivalent shown
 * beside it. Rations are balanced, costed and shared out in kilos, so the
 * nutrition panel and % of intake always run on the kilo equivalent.
 *
 * The figures are the server's (`feeding/_units.py`, through `feed_units` and
 * `herd_rations.units`): kilos per unit read off the item's own conversion
 * table, never guessed. "Kg" and "Kilogram" are both the kilogram (`isKg`).
 */

export type UnitOption = {
  uom: string;
  /** Stock units per one of this unit. */
  factor: number | null;
  /** Kilograms in one of this unit, or null where nothing says. */
  kg: number | null;
};
export type ItemUnits = { stock_uom: string; uoms: UnitOption[] };
export type UnitsMap = Record<string, ItemUnits>;

const KG_NAMES = ["kg", "kilogram", "kgs", "kilograms"];
const DOSES = ["Gram", "Millilitre"];

/** Is this unit the kilogram, whatever the site calls it ("Kg", "Kilogram")? */
export function isKg(uom: string | null | undefined): boolean {
  return KG_NAMES.includes((uom || "").trim().toLowerCase());
}

/** SI mass units that need no table. */
const SI_KG: Record<string, number> = { gram: 0.001, g: 0.001, tonne: 1000, milligram: 0.000001 };

/** Kilograms in one `uom` of `item`, or null where nothing says. A per-head
 *  dose (g, ml) is not weighed and answers null. */
export function kgPerUnit(units: UnitsMap, item: string, uom: string | null | undefined): number | null {
  if (!uom || isKg(uom)) return 1;
  if (DOSES.includes(uom)) return null;
  const opt = units[item]?.uoms.find((o) => o.uom === uom);
  if (opt?.kg) return opt.kg;
  const si = SI_KG[uom.trim().toLowerCase()];
  return si ?? null;
}

/** The units other than kilos a line of `item` may be written in: its stock
 *  unit and its conversion table, kilogram rows and doses left out. */
export function storeUnits(units: UnitsMap, item: string): UnitOption[] {
  return (units[item]?.uoms ?? []).filter((o) => !isKg(o.uom) && !DOSES.includes(o.uom));
}

/** What a stock unit is per kilo, for "≈ 0.07 bale" beside a kilo line. */
export function stockEquivalent(
  units: UnitsMap,
  item: string,
  kilos: number,
): { qty: number; uom: string } | null {
  const u = units[item];
  if (!u || !u.stock_uom || isKg(u.stock_uom)) return null;
  const per = kgPerUnit(units, item, u.stock_uom);
  if (!per) return null;
  return { qty: Math.round((kilos / per) * 1000) / 1000, uom: u.stock_uom };
}

const FEED_UNITS = "upande_livestock.serverscripts.feeding.feed_units.feed_units";

export function feedUnits(items: string[]): Promise<Envelope<{ units: UnitsMap }>> {
  return call(FEED_UNITS, { items: JSON.stringify(items) });
}

/**
 * The units of every item in `codes`, fetched once per item. `seed` is what a
 * page already has (`herd_rations.units`), so a ration loaded from it costs no
 * second request.
 */
export function useFeedUnits(codes: string[], seed?: UnitsMap): UnitsMap {
  const [fetched, setFetched] = useState<UnitsMap>({});
  const known = useMemo(() => ({ ...(seed || {}), ...fetched }), [seed, fetched]);
  const missing = useMemo(
    () => [...new Set(codes.filter((c) => c && !(c in known)))].sort(),
    [codes, known],
  );
  const key = missing.join("|");
  useEffect(() => {
    if (!key) return;
    let live = true;
    const want = key.split("|");
    feedUnits(want).then((r) => {
      if (!live || isError(r)) return;
      // Items the server did not answer for are remembered as unitless, so
      // they are not asked for again on every render.
      const got: UnitsMap = { ...(r.units || {}) };
      for (const c of want) if (!got[c]) got[c] = { stock_uom: "", uoms: [] };
      setFetched((s) => ({ ...s, ...got }));
    });
    return () => {
      live = false;
    };
  }, [key]);
  return known;
}
