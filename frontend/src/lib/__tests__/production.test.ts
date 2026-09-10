import { describe, expect, it } from "vitest";
import { niceCeil, tickIndices } from "@/components/dashboard/MilkChart";
import { ALL_HERDS, dailySeries, perCow, shiftISO, type MilkRecording } from "@/lib/production";

/** Two milkings a day, two herds, four days. */
const rows = [
  { recording_date: "2026-09-08", herd_label: "Main", session: "Evening", net_yield_kg: 400, total_yield_kg: 410, discarded_kg: 10, cows_milked: 40 },
  { recording_date: "2026-09-08", herd_label: "Main", session: "Morning", net_yield_kg: 600, total_yield_kg: 600, discarded_kg: 0, cows_milked: 40 },
  { recording_date: "2026-09-07", herd_label: "Main", session: "Morning", net_yield_kg: 500, total_yield_kg: 500, discarded_kg: 0, cows_milked: 39 },
  { recording_date: "2026-09-07", herd_label: "Weaners", session: "Morning", net_yield_kg: 90, total_yield_kg: 90, discarded_kg: 0, cows_milked: 9 },
  { recording_date: "2026-08-01", herd_label: "Main", session: "Morning", net_yield_kg: 300, total_yield_kg: 300, discarded_kg: 0, cows_milked: 30 },
] as unknown as MilkRecording[];

describe("dailySeries", () => {
  it("sums the day's milkings into one point", () => {
    const days = dailySeries(rows);
    const eighth = days.find((d) => d.date === "2026-09-08");
    expect(eighth?.net_kg).toBe(1000);
    expect(eighth?.sessions).toBe(2);
  });

  it("returns days oldest first, so the line reads left to right", () => {
    expect(dailySeries(rows).map((d) => d.date)).toEqual([
      "2026-08-01",
      "2026-09-07",
      "2026-09-08",
    ]);
  });

  it("filters to one herd", () => {
    const days = dailySeries(rows, { herd: "Weaners" });
    expect(days).toHaveLength(1);
    expect(days[0].net_kg).toBe(90);
  });

  it("treats the every-herd sentinel as no filter", () => {
    expect(dailySeries(rows, { herd: ALL_HERDS })).toHaveLength(3);
  });

  it("anchors the window on the latest recording, not the wall clock", () => {
    // A farm that last filed on 2026-09-08 still sees its last two days
    // whenever this test runs.
    expect(dailySeries(rows, { days: 2 }).map((d) => d.date)).toEqual([
      "2026-09-07",
      "2026-09-08",
    ]);
  });

  it("has nothing to draw when nothing was recorded", () => {
    expect(dailySeries([], { days: 30 })).toEqual([]);
  });
});

describe("perCow", () => {
  it("never divides by a herd of none", () => {
    expect(perCow({ date: "x", net_kg: 100, total_kg: 100, discarded_kg: 0, sessions: 1, cows: 0 })).toBeNull();
    expect(perCow({ date: "x", net_kg: 100, total_kg: 100, discarded_kg: 0, sessions: 1, cows: 4 })).toBe(25);
  });
});

describe("shiftISO", () => {
  it("crosses a month boundary backwards", () => {
    expect(shiftISO("2026-09-02", -3)).toBe("2026-08-30");
  });
});

describe("the chart's scales", () => {
  it("rounds the y ceiling to something a person would choose", () => {
    expect(niceCeil(1050)).toBe(2000);
    expect(niceCeil(430)).toBe(500);
    expect(niceCeil(0)).toBe(1);
  });

  it("always labels the last day on the x axis", () => {
    const ticks = tickIndices(30);
    expect(ticks[ticks.length - 1]).toBe(29);
    expect(ticks.length).toBeLessThanOrEqual(7);
  });

  it("labels every day when there are few", () => {
    expect(tickIndices(4)).toEqual([0, 1, 2, 3]);
  });
});
