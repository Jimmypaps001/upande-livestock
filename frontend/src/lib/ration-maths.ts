/**
 * The arithmetic the recipe editors and the Feeding page do while someone
 * types, kept pure and tested so the screens only call it.
 *
 * None of it decides stock. What a ration is per head, what a dose is in the
 * item's stock unit, and what a swapped feed weighs are the server's answers
 * (`_standing_ration`, `_doses`, `feed_substitutes`); this only lets a person
 * write a ration the way Mutara's sheet writes it — kilos per head and a
 * percentage per line, doses in grams — and see the kilos before saving.
 */

/** The units a per-head dose may be written in. Mirrors `_doses.DOSE_UOMS`. */
export const DOSE_UOMS = ["Gram", "Millilitre"] as const;
export type DoseUom = (typeof DOSE_UOMS)[number];

/**
 * A recipe line's unit as the editors carry it: kilos, a per-head dose, or a
 * unit the store counts the feed in (molasses in "Litre", hay in "BALE").
 * A store unit carries `kgPer` on its row — kilos in one of it — so every sum
 * below is in kilos; a row without it counts its quantity as kilos, as the
 * server does for a unit nothing converts.
 */
export type LineUnit = "kg" | DoseUom | (string & {});

export function isDoseUom(uom: string | null | undefined): uom is DoseUom {
  return uom === "Gram" || uom === "Millilitre";
}

/** The short form a person reads beside a number. */
export function unitLabel(unit: LineUnit): string {
  return unit === "Gram" ? "g" : unit === "Millilitre" ? "ml" : unit === "kg" || !unit ? "kg" : unit;
}

/** A row the sums below read. */
type Weighed = { qty: string | number; unit?: LineUnit; kgPer?: number | null };

/** Is this row weighed (kilos or a store unit) rather than a per-head dose? */
export function isWeighed(r: { unit?: LineUnit }): boolean {
  return !isDoseUom(r.unit);
}

/** A weighed row's kilos: its quantity through `kgPer`. A dose weighs nothing here. */
export function rowKilos(r: Weighed): number {
  if (!isWeighed(r)) return 0;
  const per = r.unit && r.unit !== "kg" && r.kgPer && r.kgPer > 0 ? r.kgPer : 1;
  return n(r.qty) * per;
}

/** The quantity in `r`'s unit that weighs `kilos`, to four places. */
export function qtyForKilos(r: { unit?: LineUnit; kgPer?: number | null }, kilos: number): number {
  const per = r.unit && r.unit !== "kg" && r.kgPer && r.kgPer > 0 ? r.kgPer : 1;
  return round(kilos / per, 4);
}

const round = (n: number, places: number) => {
  const f = 10 ** places;
  return Math.round(n * f) / f;
};

const n = (v: string | number | null | undefined) => {
  const x = typeof v === "number" ? v : parseFloat(String(v ?? ""));
  return Number.isFinite(x) ? x : 0;
};

/** What the ration weighs per head: its weighed lines in kilos, doses left out. */
export function kgTotal(rows: Weighed[]): number {
  return round(
    rows.reduce((s, r) => s + rowKilos(r), 0),
    4,
  );
}

/** Each weighed line's kilos as a percentage of the total, to two places. Doses get "". */
export function percentagesOf(rows: Weighed[]): string[] {
  const total = kgTotal(rows);
  return rows.map((r) => {
    if (!isWeighed(r)) return "";
    const kg = rowKilos(r);
    if (!total || !kg) return "";
    return String(round((kg / total) * 100, 2));
  });
}

/** Kilos for `pct` per cent of `kgPerHead`, to four places. */
export function kgFromPercent(kgPerHead: string | number, pct: string | number): number {
  return round((n(kgPerHead) * n(pct)) / 100, 4);
}

/** The percentages added up — what the screen checks against 100. */
export function percentTotal(rows: Array<{ pct?: string; unit?: LineUnit }>): number {
  return round(
    rows.reduce((s, r) => (isWeighed(r) ? s + n(r.pct) : s), 0),
    2,
  );
}

/**
 * Every kilogram line rewritten from its percentage of `kgPerHead`.
 *
 * Changing the kilos per head rescales the whole ration, which is what the
 * farm means by it: the shares stay, the amounts follow. A dose is per head
 * already and does not move.
 */
export function applyPercentages<T extends { qty: string; pct?: string; unit?: LineUnit; kgPer?: number | null }>(
  rows: T[],
  kgPerHead: string | number,
): T[] {
  return rows.map((r) =>
    !isWeighed(r)
      ? r
      : {
          ...r,
          qty:
            r.pct === undefined || r.pct === ""
              ? ""
              : String(qtyForKilos(r, kgFromPercent(kgPerHead, r.pct))),
        },
  );
}

/** Rows with their percentages filled in from their kilos, for switching modes on. */
export function withPercentages<T extends { qty: string; pct?: string; unit?: LineUnit; kgPer?: number | null }>(rows: T[]): T[] {
  const pcts = percentagesOf(rows);
  return rows.map((r, i) => ({ ...r, pct: pcts[i] }));
}

/** A recipe line as the server takes it: kilos (no unit, so the row keeps
 *  the unit it is written in), a dose with its unit, or a store unit as `uom`
 *  — which the server converts with the item's own table (`_tuned_bom.row_units`). */
export function toLine(r: { item_code: string; qty: string | number; unit?: LineUnit }): {
  item_code: string;
  qty: number;
  dose_uom?: DoseUom;
  uom?: string;
} {
  const line: { item_code: string; qty: number; dose_uom?: DoseUom; uom?: string } = {
    item_code: r.item_code,
    qty: n(r.qty),
  };
  if (isDoseUom(r.unit)) line.dose_uom = r.unit;
  else if (r.unit && r.unit !== "kg") line.uom = r.unit;
  return line;
}

/** A line for the nutrition panel: always kilos (a store unit at its kilo
 *  equivalent), or a dose with its unit. */
export function toNutrientLine(r: { item_code: string; qty: string | number; unit?: LineUnit; kgPer?: number | null }): {
  item_code: string;
  qty: number;
  dose_uom?: DoseUom;
} {
  if (isDoseUom(r.unit)) return { item_code: r.item_code, qty: n(r.qty), dose_uom: r.unit };
  return { item_code: r.item_code, qty: round(rowKilos(r), 4) };
}

/** The unit a saved line is carried in on screen: a dose stays a dose, either
 *  name of the kilogram is "kg", and any other unit is the store unit. */
export function unitFromUom(uom: string | null | undefined, isDose?: boolean): LineUnit {
  if (isDoseUom(uom) && isDose !== false) return uom;
  const u = (uom || "").trim().toLowerCase();
  if (!u || u === "kg" || u === "kilogram" || u === "kgs" || u === "kilograms") return "kg";
  return uom as string;
}

/**
 * What a per-head dose comes to for a herd, in the larger unit, for display.
 * 7 g x 300 head is 2.1 kg; 60 ml x 40 head is 2.4 L. The BOM's own
 * conversion to the item's stock unit is the server's (`_doses`).
 */
export function doseForHerd(qty: string | number, unit: DoseUom, heads: number): string {
  const total = n(qty) * (heads || 0);
  if (unit === "Gram") return total >= 1000 ? `${round(total / 1000, 3)} kg` : `${round(total, 2)} g`;
  return total >= 1000 ? `${round(total / 1000, 3)} L` : `${round(total, 2)} ml`;
}

/** Head count x per head x portion: the suggestion shown when the farm types totals. */
export function suggestedTotal(perHead: number, heads: number, portion = 1): number {
  return round(n(perHead) * n(heads) * (n(portion) || 1), 3);
}

/**
 * Kilos of a substitute for `qty` kilos of the feed it replaces, given the
 * server's `factor` (kilos of it per kilo, worked out on dry matter). Three
 * places: a mixer is not weighed to the gram.
 */
export function swapKg(qty: string | number, factor: number | null | undefined): number | null {
  if (!factor || factor <= 0) return null;
  return round(n(qty) * factor, 3);
}
