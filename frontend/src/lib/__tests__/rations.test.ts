import { describe, expect, it } from "vitest";
import {
  groupByHerd,
  milkColumnLabel,
  milkCoverage,
  recipesUsed,
  type RationRow,
} from "@/lib/rations";

/** The real shape kaitet returns, including the thing that makes this page
 *  worth building: 0-2 was fed BOM-TMR Calves Meal-005 while its standing
 *  ration is now -011, and two BOMs share the item name "TMR Calves Meal". */
function row(over: Partial<RationRow>): RationRow {
  return {
    fed_on: "2026-07-10",
    herd: "0-2",
    herd_label: "0-2",
    bom_no: "BOM-TMR Calves Meal-005",
    item_code: "TMR Calves Meal",
    recipe: "TMR Calves Meal",
    ration_kind: "",
    qty: 108,
    uom: "Kilogram",
    runs: 1,
    heads: 12,
    feed_mode: "",
    milk_kg: null,
    milk_days: 0,
    ...over,
  };
}

describe("milkColumnLabel", () => {
  it("uses the server's own label, so the heading cannot outlive the window", () => {
    expect(milkColumnLabel("same_day", "milk next day")).toBe("milk next day");
  });

  it("still names the window when the server sent no label", () => {
    expect(milkColumnLabel("next_day")).toBe("milk next day");
    expect(milkColumnLabel("avg_three")).toContain("average");
  });

  it("never falls back to a bare 'milk' for a window it knows", () => {
    for (const w of ["same_day", "next_day", "plus_two", "avg_three"]) {
      expect(milkColumnLabel(w)).not.toBe("milk");
    }
  });
});

describe("groupByHerd", () => {
  const rows = [
    row({ herd: "Lactating group 1", herd_label: "Lactating group 1", fed_on: "2026-07-09" }),
    row({ fed_on: "2026-07-09" }),
    row({ herd: "Lactating group 1", herd_label: "Lactating group 1", fed_on: "2026-07-13" }),
    row({ fed_on: "2026-07-11" }),
  ];

  it("reads each herd's days newest first", () => {
    const groups = groupByHerd(rows);
    expect(groups.map((g) => g.herd)).toEqual(["Lactating group 1", "0-2"]);
    expect(groups[0].rows.map((r) => r.fed_on)).toEqual(["2026-07-13", "2026-07-09"]);
    expect(groups[1].rows.map((r) => r.fed_on)).toEqual(["2026-07-11", "2026-07-09"]);
  });

  it("keeps the server's herd order rather than sorting alphabetically", () => {
    expect(groupByHerd(rows)[0].herd).toBe("Lactating group 1");
  });
});

describe("recipesUsed", () => {
  it("separates two recipes that share an item name", () => {
    const used = recipesUsed([
      row({ bom_no: "BOM-TMR Calves Meal-005", fed_on: "2026-07-09", qty: 100 }),
      row({ bom_no: "BOM-TMR Calves Meal-011", fed_on: "2026-08-26", qty: 180 }),
      row({ bom_no: "BOM-TMR Calves Meal-005", fed_on: "2026-07-10", qty: 8 }),
    ]);
    expect(used.map((u) => u.bom_no)).toEqual([
      "BOM-TMR Calves Meal-011",
      "BOM-TMR Calves Meal-005",
    ]);
    expect(used[1].days).toBe(2);
    expect(used[1].qty).toBe(108);
    expect(used[1].last_fed).toBe("2026-07-10");
  });
});

describe("milkCoverage", () => {
  it("counts a recorded zero as recorded and a missing figure as missing", () => {
    expect(
      milkCoverage([
        row({ milk_kg: 1000 }),
        row({ milk_kg: 0 }),
        row({ milk_kg: null }),
      ]),
    ).toEqual({ withMilk: 2, total: 3 });
  });
});
