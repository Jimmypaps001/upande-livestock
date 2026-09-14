import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The feed projection, actually rendered.
 *
 * It is a tab on the Dashboard now rather than a page of its own — milk and
 * feed are the same question asked from two ends — so this renders the body
 * without the page shell, which is exactly how the Dashboard hosts it.
 *
 * What this catches that a type check cannot: a chart that throws on a feed
 * with no stock, and a page that reports a feed nobody draws as an emergency.
 */

const items = [
  {
    item_code: "4040010091",
    item_name: "Sorghum Silage (Bargrazer)",
    uom: "Kilogram",
    on_hand: 0,
    per_day: 572,
    direct_per_day: 572,
    via_concentrate_per_day: 0,
    days_cover: 0,
    runs_out_on: "2026-09-14",
    within_horizon: true,
    herds: [{ herd: "Lactating group 1", heads: 69, per_head: 5, per_day: 345 }],
    concentrates: [],
    series: Array.from({ length: 31 }, () => 0),
  },
  {
    item_code: "4040010020",
    item_name: "Wheat Bran",
    uom: "Kilogram",
    on_hand: 14046,
    per_day: 486,
    direct_per_day: 0,
    via_concentrate_per_day: 486,
    days_cover: 28.9,
    runs_out_on: "2026-10-12",
    within_horizon: true,
    herds: [],
    concentrates: [{ concentrate: "Calves Meal", per_day: 16.2 }],
    series: Array.from({ length: 31 }, (_, i) => Math.max(14046 - 486 * i, 0)),
  },
];

const projection = {
  ok: true,
  start: "2026-09-14",
  days: 30,
  dates: Array.from({ length: 31 }, (_, i) => `2026-09-${String(14 + i).padStart(2, "0")}`),
  basis: "today's head counts and today's rations",
  items,
  running_out: items,
};

/** What the forward view answers: the same feeds, but with the herds moved on. */
const forecast = {
  ok: true,
  start: "2026-09-14",
  days: 30,
  dates: projection.dates,
  basis: "today's herds, moved forward by the farm's own rules",
  herds: {
    // 0-2 drains as its calves age out; 2-4 fills from it. The two lines are
    // the story the twenty-eight-row list was hiding.
    "0-2": Array.from({ length: 31 }, (_, i) => Math.max(0, 13 - i)),
    "2-4": Array.from({ length: 31 }, (_, i) => 10 + Math.min(i, 13)),
    BULLS: Array.from({ length: 31 }, () => 12),
  },
  items: items.map((i) => ({
    item_code: i.item_code,
    item_name: i.item_name,
    uom: i.uom,
    on_hand: i.on_hand,
    per_day: i.per_day,
    per_day_at_horizon: i.per_day * 0.8,
    drift: -i.per_day * 0.2,
    needed_total: i.per_day * 30,
    runs_out_on: i.runs_out_on,
    series: i.series,
    remaining: i.series,
  })),
  events: [
    {
      on: "2026-09-20",
      overdue: false,
      what: [{ kind: "move", from_herd: "0-2", to_herd: "2-4", heads: 3 }],
    },
  ],
};

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return {
    ...actual,
    call: vi.fn(async (method?: string) =>
      String(method || "").includes("feed_forecast") ? forecast : projection,
    ),
  };
});

const { ProjectionBody } = await import("@/pages/Projection");

function draw() {
  return render(
    <TooltipProvider>
      <ToastProvider>
      <ProjectionBody />
    </ToastProvider>
    </TooltipProvider>,
  );
}

describe("the feed projection page", () => {
  beforeEach(() => vi.clearAllMocks());

  it("leads with the date, not the quantity", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("2026-10-12")).toBeTruthy());
  });

  it("calls out a feed being drawn with nothing on hand", async () => {
    // The real finding on kaitet.local the day this was written.
    draw();
    await waitFor(() =>
      expect(screen.getByText(/being drawn every day with nothing on hand/)).toBeTruthy(),
    );
  });

  it("names what is next to go", async () => {
    draw();
    await waitFor(() => expect(screen.getAllByText(/Wheat Bran/).length).toBeGreaterThan(0));
  });

  it("states the assumption it rests on rather than implying certainty", async () => {
    draw();
    await waitFor(() =>
      expect(screen.getByText(/today's head counts and today's rations/)).toBeTruthy(),
    );
  });

  it("draws a chart even when a feed has fallen to nothing", async () => {
    // A zero-stock series is a divide-by-zero waiting to happen in the scaling.
    // Two charts on the page now, so the feed one is named rather than assumed.
    draw();
    await waitFor(() =>
      expect(
        screen
          .getAllByRole("img")
          .some((c) => (c.getAttribute("aria-label") || "").includes("Feed stock remaining")),
      ).toBe(true),
    );
  });
});


describe("what changes between now and then", () => {
  it("draws where the animals will be rather than listing every move", async () => {
    // Twenty-three days of changes, twenty-eight of them on one morning, came
    // out as "1 from 0-2 to 2-4" twenty-eight times: every fact present and
    // none of them readable.
    draw();
    await waitFor(() => expect(screen.getByText("Where the animals will be")).toBeTruthy());
    const charts = screen.getAllByRole("img");
    expect(
      charts.some((c) => (c.getAttribute("aria-label") || "").includes("Head count per herd")),
    ).toBe(true);
  });

  it("leaves out a herd that does not change size", async () => {
    // Eleven flat lines would bury the two that are doing something.
    draw();
    const chart = await waitFor(() => {
      const found = screen
        .getAllByRole("img")
        .find((c) => (c.getAttribute("aria-label") || "").includes("Head count per herd"));
      expect(found).toBeTruthy();
      return found!;
    });
    const label = chart.getAttribute("aria-label") || "";
    expect(label).toContain("0-2");
    expect(label).not.toContain("BULLS");
  });

  it("still says what moves, one row per route rather than per animal", async () => {
    draw();
    await waitFor(() => expect(screen.getByText(/3 0-2 → 2-4/)).toBeTruthy());
  });

  it("says what the draw becomes, not only what it is", async () => {
    draw();
    await waitFor(() => expect(screen.getByText(/Draw in 30 days/)).toBeTruthy());
  });
});
