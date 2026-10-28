import { describe, expect, it } from "vitest";
import {
  averageGain,
  groupByHerd,
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
    ...over,
  };
}

describe("groupByHerd", () => {
  const rows = [
    row({ herd: "Finishing group 1", herd_label: "Finishing group 1", fed_on: "2026-07-09" }),
    row({ fed_on: "2026-07-09" }),
    row({ herd: "Finishing group 1", herd_label: "Finishing group 1", fed_on: "2026-07-13" }),
    row({ fed_on: "2026-07-11" }),
  ];

  it("reads each herd's days newest first", () => {
    const groups = groupByHerd(rows);
    expect(groups.map((g) => g.herd)).toEqual(["Finishing group 1", "0-2"]);
    expect(groups[0].rows.map((r) => r.fed_on)).toEqual(["2026-07-13", "2026-07-09"]);
    expect(groups[1].rows.map((r) => r.fed_on)).toEqual(["2026-07-11", "2026-07-09"]);
  });

  it("keeps the server's herd order rather than sorting alphabetically", () => {
    expect(groupByHerd(rows)[0].herd).toBe("Finishing group 1");
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

describe("averageGain", () => {
  it("counts each ration period once, not once per feed day", () => {
    // A 10-day period at 1.0 kg/day (20 head) and a 1-day period at 0.5 (10 head).
    const long = Array.from({ length: 10 }, (_, i) =>
      row({
        fed_on: `2026-07-${String(i + 1).padStart(2, "0")}`,
        avg_adg_kg: 1.0,
        weighed_head: 20,
        period_start: "2026-07-01",
        period_end: "2026-07-10",
      }),
    );
    const short = row({
      fed_on: "2026-07-11",
      bom_no: "BOM-B",
      avg_adg_kg: 0.5,
      weighed_head: 10,
      period_start: "2026-07-11",
      period_end: "2026-07-11",
    });
    // (1.0*20 + 0.5*10) / 30, not the day-row-weighted (1.0*200 + 0.5*10) / 210.
    expect(averageGain([...long, short])).toBeCloseTo(25 / 30, 6);
  });

  it("skips periods with no gain and returns null when none has one", () => {
    expect(averageGain([row({ avg_adg_kg: null, weighed_head: 0 })])).toBeNull();
    expect(averageGain([])).toBeNull();
  });
});
