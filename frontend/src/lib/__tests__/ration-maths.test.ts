import { describe, expect, it } from "vitest";
import {
  applyPercentages,
  doseForHerd,
  isDoseUom,
  kgFromPercent,
  kgTotal,
  percentTotal,
  percentagesOf,
  qtyForKilos,
  rowKilos,
  toNutrientLine,
  unitFromUom,
  suggestedTotal,
  swapKg,
  toLine,
  unitLabel,
  withPercentages,
  type LineUnit,
} from "@/lib/ration-maths";
import { isKg, kgPerUnit, stockEquivalent, storeUnits } from "@/lib/units";

type R = { qty: string; pct?: string; unit?: LineUnit };

describe("percentage mode", () => {
  const rows: R[] = [
    { qty: "15", unit: "kg" },
    { qty: "5", unit: "kg" },
    { qty: "7", unit: "Gram" },
  ];

  it("weighs the kilos and leaves doses out", () => {
    expect(kgTotal(rows)).toBe(20);
  });

  it("states each kilogram line as a share of the kilos", () => {
    expect(percentagesOf(rows)).toEqual(["75", "25", ""]);
  });

  it("turns a percentage of kg per head into kilos", () => {
    expect(kgFromPercent(18, 62.5)).toBe(11.25);
    expect(kgFromPercent("", 50)).toBe(0);
  });

  it("rescales every kilogram line when the kilos per head change, doses untouched", () => {
    const pct = withPercentages(rows);
    const out = applyPercentages(pct, 24);
    expect(out.map((r) => r.qty)).toEqual(["18", "6", "7"]);
  });

  it("adds the percentages so the screen can hold them to 100", () => {
    expect(percentTotal([{ pct: "60" }, { pct: "35.5" }, { pct: "9", unit: "Gram" }])).toBe(95.5);
  });

  it("a line with no percentage has no kilos", () => {
    expect(applyPercentages([{ qty: "4", pct: "" }], 20)[0].qty).toBe("");
  });
});

describe("doses", () => {
  it("knows its units", () => {
    expect(isDoseUom("Gram")).toBe(true);
    expect(isDoseUom("Millilitre")).toBe(true);
    expect(isDoseUom("Kilogram")).toBe(false);
    expect(unitLabel("Millilitre")).toBe("ml");
  });

  it("sends a dose with its unit and a kilogram line without one", () => {
    expect(toLine({ item_code: "dv", qty: "7", unit: "Gram" })).toEqual({ item_code: "dv", qty: 7, dose_uom: "Gram" });
    expect(toLine({ item_code: "bran", qty: "2", unit: "kg" })).toEqual({ item_code: "bran", qty: 2 });
  });

  it("says what a dose comes to for the herd in the larger unit", () => {
    expect(doseForHerd(7, "Gram", 300)).toBe("2.1 kg");
    expect(doseForHerd(60, "Millilitre", 40)).toBe("2.4 L");
    expect(doseForHerd(25, "Gram", 10)).toBe("250 g");
  });
});

describe("the Feeding page's numbers", () => {
  it("suggests head count x per head x portion", () => {
    expect(suggestedTotal(20, 40)).toBe(800);
    expect(suggestedTotal(20, 40, 0.5)).toBe(400);
  });

  it("swaps on the server's dry-matter factor", () => {
    expect(swapKg(10, 1.5)).toBe(15);
    expect(swapKg("8", 0.666667)).toBe(5.333);
    expect(swapKg(10, null)).toBeNull();
  });
});

describe("a line in the store's unit", () => {
  // 3 Litre of molasses at 1.4 kg a litre, beside 15 kg of silage and a dose.
  const rows = [
    { qty: "15", unit: "kg" as LineUnit },
    { qty: "3", unit: "Litre" as LineUnit, kgPer: 1.4 },
    { qty: "7", unit: "Gram" as LineUnit },
  ];

  it("weighs its kilo equivalent, the dose left out", () => {
    expect(kgTotal(rows)).toBe(19.2);
    expect(rowKilos(rows[1])).toBeCloseTo(4.2);
    expect(rowKilos(rows[2])).toBe(0);
  });

  it("takes its share of intake by kilos, and gets its quantity back in litres", () => {
    expect(percentagesOf(rows)).toEqual(["78.13", "21.87", ""]);
    const out = applyPercentages(withPercentages(rows.map((r) => ({ ...r, pct: "" }))), 38.4);
    expect(Number(out[1].qty)).toBeCloseTo(6, 2);
    expect(out[2].qty).toBe("7");
  });

  it("keeps its kilos when written in another unit", () => {
    expect(qtyForKilos({ unit: "BALE", kgPer: 1 / 0.07 }, 1.5)).toBe(0.105);
    expect(qtyForKilos({ unit: "kg" }, 4.2)).toBe(4.2);
  });

  it("goes to the server with its unit, and to the nutrition in kilos", () => {
    expect(toLine({ item_code: "m", qty: "3", unit: "Litre" })).toEqual({ item_code: "m", qty: 3, uom: "Litre" });
    expect(toLine({ item_code: "s", qty: "15", unit: "kg" })).toEqual({ item_code: "s", qty: 15 });
    expect(toNutrientLine({ item_code: "m", qty: "3", unit: "Litre", kgPer: 1.4 })).toEqual({ item_code: "m", qty: 4.2 });
    expect(toNutrientLine({ item_code: "d", qty: "7", unit: "Gram" })).toEqual({ item_code: "d", qty: 7, dose_uom: "Gram" });
  });

  it("reads Kg and Kilogram both as kilos", () => {
    expect(unitFromUom("Kg")).toBe("kg");
    expect(unitFromUom("Kilogram")).toBe("kg");
    expect(unitFromUom("BALE")).toBe("BALE");
    expect(unitFromUom("Gram", true)).toBe("Gram");
    expect(unitLabel("Litre")).toBe("Litre");
  });
});

describe("the units a feed comes in", () => {
  const units = {
    hay: { stock_uom: "BALE", uoms: [{ uom: "BALE", factor: 1, kg: 1 / 0.07 }, { uom: "Kilogram", factor: 0.07, kg: 1 }] },
  };

  it("knows a kilo by either name, and a bale by the item's table", () => {
    expect(isKg("Kg")).toBe(true);
    expect(isKg("Kilogram")).toBe(true);
    expect(isKg("Litre")).toBe(false);
    expect(kgPerUnit(units, "hay", "Kg")).toBe(1);
    expect(kgPerUnit(units, "hay", "BALE")).toBeCloseTo(14.2857, 3);
    expect(kgPerUnit(units, "hay", "Gram")).toBeNull();
    expect(kgPerUnit(units, "hay", "Drum")).toBeNull();
  });

  it("offers the store units, not the kilogram row", () => {
    expect(storeUnits(units, "hay").map((u) => u.uom)).toEqual(["BALE"]);
  });

  it("says a kilo line in the store's unit", () => {
    expect(stockEquivalent(units, "hay", 1.5)).toEqual({ qty: 0.105, uom: "BALE" });
    expect(stockEquivalent({ s: { stock_uom: "Kg", uoms: [] } }, "s", 2)).toBeNull();
  });
});
