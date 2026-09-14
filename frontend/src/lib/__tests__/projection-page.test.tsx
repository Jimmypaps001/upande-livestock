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

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call: vi.fn(async () => projection) };
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
    draw();
    await waitFor(() => expect(screen.getByRole("img")).toBeTruthy());
  });
});
