import { describe, expect, it } from "vitest";
import {
  manualRowsDirty,
  PORTIONS,
  runKg,
  seedManualRows,
  seedRowsFromRecipe,
  type FeedDayStatus,
  type FeedingProgram,
  type ManualRow,
  type Recipe,
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

/** A recipe as `herd_recipes` returns it — lines already per-head, in recipe
 *  uom, exactly the real output verified against kaitet.local. */
const recipe = {
  bom_no: "BOM-Lactating Group 1-015",
  item_code: "Lactating Group 1",
  item_name: "Lactating Group 1",
  kind: "Standing",
  is_standing: true,
  created: "2026-09-04 02:30:04.152679",
  per_head_qty: 1,
  uom: "Kilogram",
  lines: [
    { item_code: "4040010082", item_name: "Silage - Farm Produced", qty: 35, uom: "Kilogram" },
    { item_code: "4040010034", item_name: "Hay - Pure Boma Rhode (15kgs Min.)", qty: 2, uom: "Kilogram" },
    { item_code: "4040010086", item_name: "Westwood Dairy Meal - New formulation", qty: 9, uom: "Kilogram" },
  ],
} as Recipe;

describe("seedRowsFromRecipe", () => {
  it("copies qty/uom straight off the recipe's own lines — no division, no conversion", () => {
    const rows = seedRowsFromRecipe(recipe);
    expect(rows).toEqual([
      { item_code: "4040010082", item_name: "Silage - Farm Produced", uom: "Kilogram", qty: 35 },
      {
        item_code: "4040010034",
        item_name: "Hay - Pure Boma Rhode (15kgs Min.)",
        uom: "Kilogram",
        qty: 2,
      },
      {
        item_code: "4040010086",
        item_name: "Westwood Dairy Meal - New formulation",
        uom: "Kilogram",
        qty: 9,
      },
    ]);
  });
});

describe("manualRowsDirty", () => {
  const seeded: ManualRow[] = [
    { item_code: "HAY", item_name: "Hay", uom: "Kg", qty: 10 },
    { item_code: "SILAGE", item_name: "Silage", uom: "Kg", qty: 35 },
  ];

  it("is not dirty right after seeding — same rows, any order", () => {
    const current = [seeded[1], seeded[0]];
    expect(manualRowsDirty(current, seeded)).toBe(false);
  });

  it("is dirty once a quantity changes", () => {
    const current = [{ ...seeded[0], qty: 12 }, seeded[1]];
    expect(manualRowsDirty(current, seeded)).toBe(true);
  });

  it("is dirty once a row is added or removed", () => {
    expect(manualRowsDirty([seeded[0]], seeded)).toBe(true);
  });

  it("is never dirty with nothing seeded yet — there is nothing to protect", () => {
    expect(manualRowsDirty(seeded, null)).toBe(false);
    expect(manualRowsDirty(null, seeded)).toBe(false);
  });
});

describe("the portion switch", () => {
  const day = { day_kg: 5106 } as FeedDayStatus;

  it("offers exactly two positions", () => {
    expect(PORTIONS.map((p) => p.portion)).toEqual([0.5, 1]);
  });

  it("turns a portion into the kilograms the operator sees", () => {
    expect(runKg(day, 0.5)).toBe(2553);
    expect(runKg(day, 1)).toBe(5106);
  });
});
