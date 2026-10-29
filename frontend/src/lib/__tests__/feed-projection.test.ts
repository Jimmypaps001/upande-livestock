import { describe, expect, it } from "vitest";
import { daysTone, fmtDaysLeft, fmtFeed, runOutWeek, weeksOf, type FeedWeek } from "@/lib/feed-projection";

const wk = (week: number, cumulative_kg: number): FeedWeek => ({
  week, week_start: "2026-11-02", feed_kg: 100, cumulative_kg, head: 1, exits: 0, avg_kg: 300, live_kg: 300,
});

describe("feed projection helpers", () => {
  it("formats feed in kg, and in tonnes from ten tonnes up", () => {
    expect(fmtFeed(5956.4)).toBe("5,956 kg");
    expect(fmtFeed(146500)).toBe("146.5 t");
    expect(fmtFeed(null)).toBe("—");
    expect(fmtFeed(0)).toBe("0 kg");
  });

  it("says days left in words, and null as beyond the horizon", () => {
    expect(fmtDaysLeft(25.2, 12)).toBe("25 days");
    expect(fmtDaysLeft(0.3, 12)).toBe("under a day");
    expect(fmtDaysLeft(null, 12)).toBe("beyond 12 weeks");
  });

  it("draws under a week as short and under two as a warning", () => {
    expect(daysTone(3)).toBe("short");
    expect(daysTone(10)).toBe("warn");
    expect(daysTone(30)).toBe("ok");
    expect(daysTone(null)).toBe("ok");
  });

  it("finds the week the stock runs out", () => {
    const weeks = [wk(1, 100), wk(2, 200), wk(3, 300)];
    expect(runOutWeek(weeks, 150)).toBe(2);
    expect(runOutWeek(weeks, 300)).toBeNull();
  });

  it("reads a scenario's weeks, none when the herd has none", () => {
    expect(weeksOf({ weeks: null }, "low")).toEqual([]);
    const w = [wk(1, 1)];
    expect(weeksOf({ weeks: { low: w, expected: [], high: [] } }, "low")).toBe(w);
  });
});
