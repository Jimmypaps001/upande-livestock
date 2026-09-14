import { describe, expect, it } from "vitest";
import { urgencyOf, urgencyWords, type ProjectedItem } from "@/lib/projection";

function item(over: Partial<ProjectedItem> = {}): ProjectedItem {
  return {
    item_code: "4040010082",
    item_name: "Silage - Farm Produced",
    uom: "Kilogram",
    on_hand: 90000,
    per_day: 3846,
    direct_per_day: 3846,
    via_concentrate_per_day: 0,
    days_cover: 23.4,
    runs_out_on: "2026-10-07",
    within_horizon: true,
    herds: [],
    concentrates: [],
    series: [],
    ...over,
  };
}

describe("how worried to be about a feed", () => {
  it("is measured in lead time, not in how full the bin looks", () => {
    // A feed 80% full is an emergency if it goes in four days and the supplier
    // takes a week; one at 5% is fine if nothing eats it.
    expect(urgencyOf(item({ days_cover: 23.4 }))).toBe("fine");
    expect(urgencyOf(item({ days_cover: 8 }))).toBe("week");
    expect(urgencyOf(item({ days_cover: 2 }))).toBe("days");
    expect(urgencyOf(item({ days_cover: 0 }))).toBe("gone");
  });

  it("treats a feed nothing draws as nothing to worry about, not as urgent", () => {
    // days_cover is null when the daily draw is zero. Sorting or colouring
    // that as "0 days left" would put a feed nobody uses at the top of the
    // worklist for ever.
    const untouched = item({ days_cover: null, runs_out_on: null, per_day: 0 });
    expect(urgencyOf(untouched)).toBe("fine");
    expect(urgencyWords(untouched)).toBe("nothing draws it");
  });

  it("says today and tomorrow rather than a fraction of a day", () => {
    expect(urgencyWords(item({ days_cover: 0.4 }))).toBe("gone today");
    expect(urgencyWords(item({ days_cover: 1.6 }))).toBe("gone tomorrow");
    expect(urgencyWords(item({ days_cover: 0 }))).toBe("none left");
  });

  it("rounds down, because a part day is not a day you can buy in", () => {
    expect(urgencyWords(item({ days_cover: 3.9 }))).toBe("3 days left");
  });
});
