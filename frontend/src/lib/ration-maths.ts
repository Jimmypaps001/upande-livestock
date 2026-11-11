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

// ---------------------------------------------------------------------------
// Kilos and shares, both editable, with locks
// ---------------------------------------------------------------------------
//
// THE RULE (docs/client/using-livestock/06-feeding.md, "Kilos and shares").
//
// Every weighed line has its kilos (in its own unit) and its share of intake,
// and either may be typed. Whether the shares hold depends on whether the
// ration has a DEFINITE total: kilos per head per day (per batch, for a
// concentrate) that the person has typed in.
//
// * With a definite total, typing a line's kilos or its % LOCKS that line.
//   The total does not move: every UNLOCKED line other than the one typed in
//   is rescaled, in proportion to what it has now, so the recipe adds up to
//   exactly the total and to 100%. Lines locked earlier keep their figures.
//   When the locked lines leave nothing for this one, or no unlocked line is
//   left to take up the change, the figure is clamped to what is available
//   and `notice` says why, rather than the total quietly breaking.
// * With no definite total, typing a line's kilos changes that line only;
//   the total is the sum and every share is worked out again. Nothing locks.
// * Typing a % always locks: with no definite total, the current sum BECOMES
//   the definite total (the kg-per-head field is filled in with it), and the
//   line locks and rebalances as above.
// * Changing the total keeps every line's % (locked lines included) and the
//   kilos follow. The farm thinks of a ration in shares of intake ("18 kg a
//   head: silage 62.5%..."), so moving a group up to 20 kg keeps its mix.
//   Clearing the total drops every lock: a lock only means something against
//   a definite total.
// * Adding a line with a definite total starts it at nothing, unlocked;
//   taking a line out hands its share to the unlocked lines.
// * Kilos are kept to 3 places and % to 2; the last unlocked line takes up
//   the rounding so the lines add up exactly. A line in a store unit (Litre,
//   BALE) is balanced in kilos; its quantity is those kilos in its unit, to 4
//   places. A figure typed in is kept as typed.
// * Per-head doses (g, ml) are outside the 100% and outside all of this.
//
// Locks are screen state: they are not saved. A recipe is saved as lines of
// kilos (or a store unit, or a dose), which is all a BOM holds.

/** A line the balancing below works on. `locked` is screen state only. */
export type BalanceRow = {
  qty: string;
  pct?: string;
  unit?: LineUnit;
  kgPer?: number | null;
  locked?: boolean;
};

/** The rows after a change, the total (kg per head) and what to tell the person. */
export type Balanced<T> = { rows: T[]; total: string; notice: string | null };

const kg3 = (x: number) => round(x, 3);
const pc2 = (x: number) => round(x, 2);
const say = (x: number) => String(kg3(x));

/** Has the person given the ration a total to hold to? */
export function hasDefiniteTotal(total: string | number | null | undefined): boolean {
  return n(total) > 0;
}

/**
 * Each weighed line's share of the kilos, to two places, the last line with
 * kilos taking up the rounding so they add up to exactly 100. Doses and lines
 * with no kilos get "".
 */
export function sharesOf(rows: Weighed[]): string[] {
  const total = kgTotal(rows);
  const out = rows.map(() => "");
  if (!total) return out;
  const filled = rows.map((r, i) => (isWeighed(r) && rowKilos(r) > 0 ? i : -1)).filter((i) => i >= 0);
  let sum = 0;
  filled.forEach((i, j) => {
    const p = j === filled.length - 1 ? pc2(100 - sum) : pc2((rowKilos(rows[i]) / total) * 100);
    sum += p;
    out[i] = String(p);
  });
  return out;
}

/** The rows with their shares worked out from their kilos and no locks: how
 *  a recipe stands when there is no definite total. */
export function unheld<T extends BalanceRow>(rows: T[]): T[] {
  const shares = sharesOf(rows);
  return rows.map((r, i) => ({ ...r, pct: shares[i], locked: false }));
}

/** `r` at `kilos`, its quantity in its own unit; nothing is written as "". */
function atKilos<T extends BalanceRow>(r: T, kilos: number, pct: number | string): T {
  return { ...r, qty: kilos > 0 ? String(qtyForKilos(r, kilos)) : "", pct: String(pct) };
}

/**
 * Share `kilos` (and `pct` of the total) between the lines at `idx`, in
 * proportion to their kilos now (or their %, or evenly where they have
 * neither), the last one taking up the rounding.
 */
function spread<T extends BalanceRow>(out: T[], idx: number[], kilos: number, pct: number) {
  if (!idx.length) return;
  if (kilos <= 0) {
    for (const i of idx) out[i] = atKilos(out[i], 0, 0);
    return;
  }
  let w = idx.map((i) => rowKilos(out[i]));
  if (w.reduce((a, b) => a + b, 0) <= 0) w = idx.map((i) => n(out[i].pct));
  if (w.reduce((a, b) => a + b, 0) <= 0) w = idx.map(() => 1);
  const wSum = w.reduce((a, b) => a + b, 0);
  let kSum = 0;
  let pSum = 0;
  idx.forEach((i, j) => {
    const last = j === idx.length - 1;
    const k = last ? Math.max(0, kg3(kilos - kSum)) : kg3((kilos * w[j]) / wSum);
    // A line's % is its part of `pct`, as its kilos are of `kilos`, so the
    // two stay in step and the last line's remainder cannot go below nothing.
    const p = last ? Math.max(0, pc2(pct - pSum)) : pc2((pct * k) / kilos);
    kSum += k;
    pSum += p;
    out[i] = atKilos(out[i], k, p);
  });
}

function weighedIndexes(rows: BalanceRow[]): number[] {
  return rows.map((r, i) => (isWeighed(r) ? i : -1)).filter((i) => i >= 0);
}

/**
 * A line's kilos (`field` "qty", in its own unit) or its % (`field` "pct")
 * typed in. See THE RULE above.
 */
export function editLine<T extends BalanceRow>(
  rows: T[],
  total: string,
  index: number,
  field: "qty" | "pct",
  value: string,
): Balanced<T> {
  const r = rows[index];
  if (!r) return { rows, total, notice: null };
  if (!isWeighed(r)) {
    // A dose: per head already, outside the 100%.
    return { rows: rows.map((x, i) => (i === index ? { ...x, qty: value } : x)), total, notice: null };
  }

  let T = n(total);
  let current = rows;
  if (!(T > 0)) {
    if (field === "qty") {
      return { rows: unheld(rows.map((x, i) => (i === index ? { ...x, qty: value } : x))), total, notice: null };
    }
    // A % with no total: the kilos there are now become the total.
    T = kgTotal(rows);
    if (!(T > 0)) {
      return {
        rows: rows.map((x, i) => (i === index ? { ...x, pct: value } : x)),
        total,
        notice: "Enter the kilos per head first: a share needs a total to be a share of.",
      };
    }
    total = String(T);
    current = unheld(rows);
  }

  const out = [...current];
  const weighed = weighedIndexes(current);
  const held = weighed.filter((i) => i !== index && current[i].locked);
  const free = weighed.filter((i) => i !== index && !current[i].locked);
  const heldKg = kg3(held.reduce((s, i) => s + rowKilos(current[i]), 0));
  const heldPct = pc2(held.reduce((s, i) => s + n(current[i].pct), 0));
  const availKg = kg3(T - heldKg);
  const availPct = Math.max(0, pc2(100 - heldPct));

  let k = field === "qty" ? rowKilos({ ...r, qty: value }) : (T * n(value)) / 100;
  let asTyped = true;
  let notice: string | null = null;
  if (availKg <= 0) {
    k = 0;
    asTyped = false;
    notice = `Locked rows already use ${say(heldKg)} of ${say(T)} kg — unlock a row to give this one any.`;
  } else if (k > availKg + 1e-9) {
    k = availKg;
    asTyped = false;
    notice = held.length
      ? `Locked rows already use ${say(heldKg)} of ${say(T)} kg — unlock a row to give it more.`
      : `A row cannot take more than the whole ${say(T)} kg.`;
  } else if (!free.length && Math.abs(k - availKg) > 0.0005) {
    k = availKg;
    asTyped = false;
    notice = `Every other row is locked, so this one takes the remaining ${say(availKg)} kg — unlock a row to change it.`;
  }
  k = Math.max(0, kg3(k));

  // Its %: what was typed, or its kilos' share; never more than the unlocked
  // lines have between them (kilos and % are each rounded, so they can
  // disagree by a hair at the edge). Taking everything left, it takes the
  // whole of the % left too.
  const pct = !free.length || k >= availKg
    ? availKg > 0
      ? availPct
      : 0
    : field === "pct" && asTyped && n(value) <= availPct
      ? value
      : Math.min(availPct, pc2((k / T) * 100));
  out[index] = {
    ...(asTyped && field === "qty" ? { ...r, qty: value, pct: String(pct) } : atKilos(r, k, pct)),
    locked: true,
  };
  spread(out, free, kg3(availKg - k), pc2(availPct - n(pct)));
  return { rows: out, total, notice };
}

/**
 * The kilos per head typed in (`was` is what it was). Every line keeps its %
 * (locked lines too) and its kilos follow; the last unlocked line takes up the
 * rounding. Coming from no definite total, the shares are first worked out
 * from the kilos, so the first figure typed scales the recipe. Cleared, the
 * locks go and the lines keep their kilos.
 */
export function changeTotal<T extends BalanceRow>(rows: T[], was: string, total: string): Balanced<T> {
  if (!hasDefiniteTotal(total)) return { rows: unheld(rows), total, notice: null };
  const T = n(total);
  const current = hasDefiniteTotal(was) ? rows : unheld(rows);
  const weighed = weighedIndexes(current);
  const free = weighed.filter((i) => !current[i].locked);
  const absorber = free.length ? free[free.length - 1] : -1;
  const pctSum = pc2(weighed.reduce((s, i) => s + n(current[i].pct), 0));
  const out = [...current];
  let kSum = 0;
  for (const i of weighed) {
    if (i === absorber) continue;
    const k = kg3((T * n(current[i].pct)) / 100);
    kSum += k;
    out[i] = { ...out[i], qty: k > 0 ? String(qtyForKilos(out[i], k)) : "" };
  }
  if (absorber >= 0) {
    const k = Math.max(0, kg3((T * pctSum) / 100 - kSum));
    out[absorber] = { ...out[absorber], qty: k > 0 ? String(qtyForKilos(out[absorber], k)) : "" };
  }
  const notice =
    pctSum > 0 && Math.abs(pctSum - 100) > 0.005
      ? `The shares add up to ${pctSum}%, not 100% — unlock a row so it can take up the difference.`
      : null;
  return { rows: out, total, notice };
}

/**
 * After a line is added, taken out, merged or put in another unit: with a
 * definite total the unlocked lines take up whatever is not locked, in
 * proportion to what they have; with none, the shares are worked out again.
 */
export function rebalance<T extends BalanceRow>(rows: T[], total: string): Balanced<T> {
  if (!hasDefiniteTotal(total)) return { rows: unheld(rows), total, notice: null };
  const T = n(total);
  const out = rows.map((r) => (isWeighed(r) ? r : { ...r, pct: "", locked: false }));
  const weighed = weighedIndexes(out);
  const held = weighed.filter((i) => out[i].locked);
  const free = weighed.filter((i) => !out[i].locked);
  const heldKg = kg3(held.reduce((s, i) => s + rowKilos(out[i]), 0));
  const heldPct = pc2(held.reduce((s, i) => s + n(out[i].pct), 0));
  const availKg = kg3(T - heldKg);
  let notice: string | null = null;
  if (availKg < 0) {
    notice = `Locked rows already use ${say(heldKg)} of ${say(T)} kg — unlock a row.`;
  } else if (!free.length && availKg > 0.0005) {
    notice = `Every row is locked and they come to ${say(heldKg)} of ${say(T)} kg — unlock a row so it can take up the rest.`;
  }
  spread(out, free, Math.max(0, availKg), Math.max(0, pc2(100 - heldPct)));
  return { rows: out, total, notice };
}

/** Lock or unlock a line by hand. Only against a definite total; a dose never locks. */
export function toggleLock<T extends BalanceRow>(rows: T[], index: number, total: string): T[] {
  if (!hasDefiniteTotal(total) || !rows[index] || !isWeighed(rows[index])) return rows;
  return rows.map((r, i) => (i === index ? { ...r, locked: !r.locked } : r));
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
