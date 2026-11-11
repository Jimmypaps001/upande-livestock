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

/** A recipe line's unit as the editors carry it: kilos, or a per-head dose. */
export type LineUnit = "kg" | DoseUom;

export function isDoseUom(uom: string | null | undefined): uom is DoseUom {
  return uom === "Gram" || uom === "Millilitre";
}

/** The short form a person reads beside a number. */
export function unitLabel(unit: LineUnit): string {
  return unit === "Gram" ? "g" : unit === "Millilitre" ? "ml" : "kg";
}

const round = (n: number, places: number) => {
  const f = 10 ** places;
  return Math.round(n * f) / f;
};

const n = (v: string | number | null | undefined) => {
  const x = typeof v === "number" ? v : parseFloat(String(v ?? ""));
  return Number.isFinite(x) ? x : 0;
};

/** What the ration weighs per head: its kilogram lines, doses left out. */
export function kgTotal(rows: Array<{ qty: string | number; unit?: LineUnit }>): number {
  return round(
    rows.reduce((s, r) => (r.unit && r.unit !== "kg" ? s : s + n(r.qty)), 0),
    4,
  );
}

/** Each kilogram line as a percentage of the kilos, to two places. Doses get "". */
export function percentagesOf(rows: Array<{ qty: string | number; unit?: LineUnit }>): string[] {
  const total = kgTotal(rows);
  return rows.map((r) => {
    if (r.unit && r.unit !== "kg") return "";
    if (!total || !n(r.qty)) return "";
    return String(round((n(r.qty) / total) * 100, 2));
  });
}

/** Kilos for `pct` per cent of `kgPerHead`, to four places. */
export function kgFromPercent(kgPerHead: string | number, pct: string | number): number {
  return round((n(kgPerHead) * n(pct)) / 100, 4);
}

/** The percentages added up — what the screen checks against 100. */
export function percentTotal(rows: Array<{ pct?: string; unit?: LineUnit }>): number {
  return round(
    rows.reduce((s, r) => (r.unit && r.unit !== "kg" ? s : s + n(r.pct)), 0),
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
export function applyPercentages<T extends { qty: string; pct?: string; unit?: LineUnit }>(
  rows: T[],
  kgPerHead: string | number,
): T[] {
  return rows.map((r) =>
    r.unit && r.unit !== "kg"
      ? r
      : { ...r, qty: r.pct === undefined || r.pct === "" ? "" : String(kgFromPercent(kgPerHead, r.pct)) },
  );
}

/** Rows with their percentages filled in from their kilos, for switching modes on. */
export function withPercentages<T extends { qty: string; pct?: string; unit?: LineUnit }>(rows: T[]): T[] {
  const pcts = percentagesOf(rows);
  return rows.map((r, i) => ({ ...r, pct: pcts[i] }));
}

/** A recipe line as the server takes it: kilos, or a dose with its unit. */
export function toLine(r: { item_code: string; qty: string | number; unit?: LineUnit }): {
  item_code: string;
  qty: number;
  dose_uom?: DoseUom;
} {
  const line: { item_code: string; qty: number; dose_uom?: DoseUom } = {
    item_code: r.item_code,
    qty: n(r.qty),
  };
  if (r.unit && r.unit !== "kg") line.dose_uom = r.unit;
  return line;
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
