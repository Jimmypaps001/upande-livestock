import { describe, expect, it } from "vitest";
import {
  PORTIONS,
  runKg,
  seedManualRows,
  type FeedDayStatus,
  type FeedingProgram,
} from "@/lib/feeding";

/** A 50-head herd whose ration is hay: written in kg on the BOM, stocked in
 *  BALE at 0.07 bale/kg. The two units differ by ~14x, which is the whole
 *  point of the test. */
const program = {
  herd: "HERD-0001",
  heads: 50,
  lines: [
    {
      item_code: "HAY",
      item_name: "Hay",
      uom: "BALE",
      required_qty: 35, // 500 kg x 0.07
      recipe_qty: 500, // 10 kg per head x 50
      recipe_uom: "Kg",
      conversion_factor: 0.07,
    },
  ],
} as unknown as FeedingProgram;

describe("seedManualRows", () => {
  it("seeds the per-head quantity in the recipe uom, not the stock uom", () => {
    const [hay] = seedManualRows(program);
    expect(hay.qty).toBe(10);
    expect(hay.uom).toBe("Kg");
  });

  it("never seeds from required_qty — that would issue ~14x the hay", () => {
    const [hay] = seedManualRows(program);
    expect(hay.qty).not.toBeCloseTo(35 / 50);
  });

  it("survives a herd with no head count without dividing by zero", () => {
    const rows = seedManualRows({ ...program, heads: 0 } as FeedingProgram);
    expect(Number.isFinite(rows[0].qty)).toBe(true);
  });
});

describe("the portion slider", () => {
  const day = { day_kg: 5106 } as FeedDayStatus;

  it("offers exactly two positions", () => {
    expect(PORTIONS.map((p) => p.portion)).toEqual([0.5, 1]);
  });

  it("turns a portion into the kilograms the operator sees", () => {
    expect(runKg(day, 0.5)).toBe(2553);
    expect(runKg(day, 1)).toBe(5106);
  });
});
