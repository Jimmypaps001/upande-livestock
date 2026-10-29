import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/Toast";

const week = (n: number, feed: number, cum: number, head: number, exits = 0) => ({
  week: n, week_start: `2026-11-0${n}`, feed_kg: feed, cumulative_kg: cum, head, exits, avg_kg: 300 + n, live_kg: head * (300 + n),
});
const scen = (k: number) => [week(1, 100 * k, 100 * k, 10), week(2, 100 * k, 200 * k, 9, 1)];
const herd = (o: Record<string, unknown>) => ({
  herd: "Finishers", herd_class: "Fattening", paddock: "Feedlot Pen 3 - MUT", counting: "Individual", head: 90, calves: 0,
  fed_heads: 90, weighed: 90, estimated: 0, unweighed: 0, grows: true, live_kg: 34755, avg_kg: 386, day_kg: 1390,
  stock_kg: 30000, paddock_stock_kg: 0, weeks: { low: scen(1), expected: scen(2), high: scen(3) },
  days_left: { low: 20, expected: 5, high: null, today_rate: 21 }, ...o,
});

let error: string | null = null;
const call = vi.fn(async (method?: string, args?: unknown) => {
  const m = method || "";
  if (m.endsWith("list_performance_herds")) return [{ herd: "Finishers", herd_class: "Fattening", head_count: 90 }];
  if (m.endsWith("get_feed_projection")) {
    if (error) return { error };
    return {
      as_of: "2026-10-29", weeks: (args as { weeks: number }).weeks,
      settings: { dm_intake_pct: 4, adg_min_kg: 0.7, adg_max_kg: 1.2, min_weighings: 2, min_span_days: 30, exit_weight_kg: 450 },
      total: { head: 500, fed_heads: 449, calves: 51, live_kg: 148910, day_kg: 5956, stock_kg: 146500, weeks: { low: scen(1), expected: scen(2), high: scen(3) },
        days_left: { low: 25, expected: 25.2, high: 30, today_rate: 24.6 } },
      herds: [herd({}), herd({ herd: "Lactation Group 1", herd_class: "Breeding", paddock: "Paddock A1 - MUT", head: 98, calves: 34, days_left: { low: 3, expected: 3, high: 3, today_rate: 3 } })],
      bands: { names: ["Starters", "Growers", "Finishers"], today: { Starters: 73, Growers: 62, Finishers: 115 },
        weeks: [{ week: 1, week_start: "2026-11-01", counts: { Starters: 68, Growers: 57, Finishers: 129 }, exits: 13,
          moves: [{ from: "Starters", to: "Growers", head: 5 }, { from: "Growers", to: "Finishers", head: 14 }] }] },
      stock: { total_kg: 146500, central_kg: 146500, items: [{ item_code: "Hay", item_name: "Mutara Boma Hay", kg: 45000, warehouse: "Hay Store - MUT" }], warehouses: [], uncounted: [] },
      notes: ["Intake is 4% of live weight a day."],
    };
  }
  return {};
});
vi.mock("@/lib/frappe", async () => ({ ...(await vi.importActual<object>("@/lib/frappe")), call }));

const { Forecast } = await import("@/pages/Forecast");

function draw() {
  return render(
    <TooltipProvider>
      <ToastProvider>
        <Forecast />
      </ToastProvider>
    </TooltipProvider>,
  );
}
const openFeed = () => fireEvent.mouseDown(screen.getByRole("tab", { name: "Feed" }));

describe("the Feed tab on Production Forecast", () => {
  beforeEach(() => {
    call.mockClear();
    error = null;
  });

  it("shows today's head, live weight, feed a day and the feed in store", async () => {
    draw();
    openFeed();
    await waitFor(() => expect(screen.getByTestId("feed-herds")).toBeTruthy());
    expect(screen.getAllByText("Head today")[0].parentElement!.textContent).toContain("500");
    expect(screen.getAllByText("Live weight")[0].parentElement!.textContent).toContain("148.9 t");
    expect(screen.getAllByText("Feed a day")[0].parentElement!.textContent).toContain("5,956 kg");
    expect(screen.getAllByText("Feed in store")[0].parentElement!.textContent).toContain("146.5 t");
  });

  it("asks for the selected weeks, defaulting to twelve", async () => {
    draw();
    openFeed();
    await waitFor(() => expect(call).toHaveBeenCalledWith(expect.stringContaining("get_feed_projection"), { weeks: 12 }));
  });

  it("lists days of feed left per herd, short ones in the warning tone", async () => {
    draw();
    openFeed();
    const table = await screen.findByTestId("feed-herds");
    const row = within(table).getByText("Lactation Group 1").closest("tr")!;
    expect(row.textContent).toContain("98 (34 calves)");
    expect(within(row).getByText("3 days").className).toMatch(/critical/);
    const fin = within(table).getByText("Finishers").closest("tr")!;
    expect(within(fin).getByText("5 days")).toBeTruthy();
  });

  it("shows the three days-left cases for the farm and beyond-horizon as such", async () => {
    draw();
    openFeed();
    const row = await screen.findByTestId("feed-days-left");
    expect(row.textContent).toContain("Low gain");
    expect(row.textContent).toContain("25 days");
    expect(row.textContent).toContain("30 days");
  });

  it("shows the band crossings and a store line that goes short", async () => {
    draw();
    openFeed();
    const bands = await screen.findByTestId("feed-bands");
    expect(bands.textContent).toContain("5 Starters to Growers, 14 Growers to Finishers");
    expect(screen.getByTestId("feed-weeks")).toBeTruthy();
    expect(screen.getByTestId("feed-stock").textContent).toContain("Mutara Boma Hay");
    expect(screen.getByTestId("feed-notes").textContent).toContain("Intake is 4%");
  });

  it("shows a refusal verbatim", async () => {
    error = "Not allowed to read Animal.";
    draw();
    openFeed();
    await waitFor(() => expect(screen.getByText("Not allowed to read Animal.")).toBeTruthy());
  });
});
