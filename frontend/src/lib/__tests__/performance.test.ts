import { describe, expect, it } from "vitest";
import {
  DEFAULT_PERIOD_DAYS,
  NOT_ENOUGH_WEIGHINGS,
  PERIOD_OPTIONS,
  formatAdg,
  isHighlighted,
  sortRows,
  type PerformanceRow,
} from "@/lib/performance";

function row(over: Partial<PerformanceRow> & { animal: string }): PerformanceRow {
  return {
    label: over.animal,
    latest_weight_kg: 300,
    latest_weight_date: "2026-10-01",
    days_since_weighing: 26,
    period_adg: 0.9,
    herd_adg: 0.8,
    lifetime_adg: 0.85,
    rank: 1,
    below_target: false,
    ...over,
  };
}

describe("formatAdg", () => {
  it("formats ADG as kg/day with 2 decimals", () => {
    expect(formatAdg(0.9)).toBe("0.90 kg/day");
    expect(formatAdg(1.2345)).toBe("1.23 kg/day");
    expect(formatAdg(0)).toBe("0.00 kg/day");
  });

  it('shows "Not enough weighings" when period_adg is null', () => {
    expect(formatAdg(null)).toBe("Not enough weighings");
    expect(NOT_ENOUGH_WEIGHINGS).toBe("Not enough weighings");
  });
});

describe("sortRows", () => {
  it("puts unranked rows last (in server order), ranked rows by rank", () => {
    const sorted = sortRows([
      row({ animal: "U1", period_adg: null, rank: null, below_target: null }),
      row({ animal: "B", rank: 2 }),
      row({ animal: "A", rank: 1 }),
      row({ animal: "U0", period_adg: null, rank: null, below_target: null }),
    ]);
    expect(sorted.map((r) => r.animal)).toEqual(["A", "B", "U1", "U0"]);
  });
});

describe("isHighlighted", () => {
  it("highlights a below-target row", () => {
    expect(isHighlighted(row({ animal: "A", below_target: true }))).toBe(true);
  });

  it("does not highlight an on-target or unranked row", () => {
    expect(isHighlighted(row({ animal: "A", below_target: false }))).toBe(false);
    expect(isHighlighted(row({ animal: "A", rank: null, period_adg: null, below_target: null }))).toBe(false);
  });
});

describe("ranking period", () => {
  it("offers 30/60/90/180 days and defaults to 90", () => {
    expect(PERIOD_OPTIONS).toEqual([30, 60, 90, 180]);
    expect(DEFAULT_PERIOD_DAYS).toBe(90);
  });
});
