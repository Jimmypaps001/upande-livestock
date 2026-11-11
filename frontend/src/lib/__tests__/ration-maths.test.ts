import { describe, expect, it } from "vitest";
import {
  applyPercentages,
  doseForHerd,
  isDoseUom,
  kgFromPercent,
  kgTotal,
  percentTotal,
  percentagesOf,
  suggestedTotal,
  swapKg,
  toLine,
  unitLabel,
  withPercentages,
  type LineUnit,
} from "@/lib/ration-maths";

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
