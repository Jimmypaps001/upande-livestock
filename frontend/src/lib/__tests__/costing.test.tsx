import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/Toast";

/**
 * Cost per animal: the helpers, the Costs page, the Daily Labour screen and
 * the Dashboard panel, against `serverscripts/costing/*`'s shapes.
 */

const day = (date: string, o: Record<string, unknown> = {}) => ({
  date, feed_cost: 1000, medicine_cost: 100, labour_cost: 2400, fuel_cost: 0, total_cost: 3500,
  animals: 100, cost_per_animal: 35, diesel_litres: 0, ...o,
});

let production = true;
let refuse = false;
/** The 1 November feed came from tracker history (Livestock Feed History), not the ledger. */
let history = false;
const report = () => ({
  ok: true,
  from_date: "2026-11-01",
  to_date: "2026-11-02",
  days: [
    day("2026-11-01", history ? { history_feed_cost: 1000, feed_from_history: true } : {}),
    day("2026-11-02", { total_cost: 0, animals: 0, cost_per_animal: null }),
  ],
  months: [{ month: "2026-11", days: 2, animal_days: 100, average_animals: 50, feed_cost: 1000,
    medicine_cost: 100, labour_cost: 2400, fuel_cost: 0, total_cost: 3500, cost_per_animal: 35,
    history_feed_cost: history ? 1000 : 0 }],
  herds: [{ herd: "Finishers", feed_cost: 1000, head_days: 80, average_heads: 40,
    feed_cost_per_head_day: 12.5, history_days: history ? 1 : 0, history_feed_cost: history ? 1000 : 0, days: [] }],
  total: { days: 2, animal_days: 100, feed_cost: 1000, medicine_cost: 100, labour_cost: 2400,
    fuel_cost: 0, total_cost: 3500, cost_per_animal: 35, history_feed_cost: history ? 1000 : 0 },
  fuel_available: production,
  fuel_note: production ? null : "upande_production is not installed.",
  production_installed: production,
  machines: production
    ? [{ allocation: "PAA-1", machine: "Tractor 1", operator: "E1", operator_name: "Jane", start_time: "2026-11-01 07:00:00",
      end_time: null, duration_hours: 3, diesel_litres: 12, diesel_cost: 2100, cost_center: "Feedlot - M" }]
    : [],
  silage: production
    ? { available: true, reason: null, cycles: [{ cycle: "SC-1", crop: "Maize", silage_item: "Maize Silage",
      status: "Closed", ensiled_kg: 100000, total_cost: 450000, cost_per_kg: 4.5 }] }
    : null,
  labour_rates: { "Feedlot workers": 400, Herders: 400, Other: 400 },
});

const labourDay = {
  ok: true, date: "2026-11-11", saved: false, name: null, notes: "",
  rows: [
    { category: "Feedlot workers", workers: 0, day_rate: 400, amount: 0, notes: "" },
    { category: "Herders", workers: 0, day_rate: 400, amount: 0, notes: "" },
  ],
  categories: ["Feedlot workers", "Herders", "Other"],
  default_rates: { "Feedlot workers": 400, Herders: 400, Other: 350 },
  recent: [{ name: "2026-11-10", date: "2026-11-10", workers: 8, amount: 3200 }],
  can_write: true,
};

const call = vi.fn(async (method?: string, args?: unknown) => {
  const m = method || "";
  void args;
  if (m.endsWith("cost_per_animal")) return refuse ? { error: "You are not permitted to read Livestock Daily Labour." } : report();
  if (m.endsWith("save_daily_labour")) return { ok: true, name: "2026-11-11", date: "2026-11-11", total_workers: 6, total_amount: 2400 };
  if (m.endsWith("daily_labour")) return labourDay;
  return {};
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Costs } = await import("@/pages/Costs");
const { Labour } = await import("@/pages/Labour");
const { CostPanel } = await import("@/components/costing/CostPanel");
const lib = await import("@/lib/costing");

function draw(node: React.ReactNode) {
  return render(
    <TooltipProvider>
      <ToastProvider>{node}</ToastProvider>
    </TooltipProvider>,
  );
}

beforeEach(() => {
  cleanup();
  call.mockClear();
  production = true;
  refuse = false;
  history = false;
});

describe("costing helpers", () => {
  it("bounds a month at today", () => {
    expect(lib.monthWindow("2026-11", "2026-11-11")).toEqual({ from: "2026-11-01", to: "2026-11-11" });
    expect(lib.monthWindow("2026-02", "2026-11-11")).toEqual({ from: "2026-02-01", to: "2026-02-28" });
  });
  it("lists recent months across a year end", () => {
    expect(lib.recentMonths("2026-01-15", 3)).toEqual(["2026-01", "2025-12", "2025-11"]);
  });
  it("formats money and the missing figure", () => {
    expect(lib.fmtMoney(1234.5)).toBe("1,235");
    expect(lib.fmtPerAnimal(35)).toBe("35.00");
    expect(lib.fmtPerAnimal(null)).toBe("—");
  });
  it("works out a labour line from the default when no rate is typed", () => {
    const d = { Herders: 400 };
    expect(lib.labourAmount({ category: "Herders", workers: 3, day_rate: null }, d)).toBe(1200);
    expect(lib.labourAmount({ category: "Herders", workers: 3, day_rate: 500 }, d)).toBe(1500);
    expect(lib.labourAmount({ category: "Herders", workers: -2, day_rate: 500 }, d)).toBe(0);
  });
  it("counts a herd's history days in words", () => {
    expect(lib.historyDaysLabel(0)).toBe("");
    expect(lib.historyDaysLabel(1)).toBe("1 day from tracker history");
    expect(lib.historyDaysLabel(12)).toBe("12 days from tracker history");
  });
  it("picks the latest day with animals and cost", () => {
    const r = report();
    expect(lib.latestCostedDay(r.days as never)?.date).toBe("2026-11-01");
    expect(lib.daysBack("2026-11-11", 7)).toBe("2026-11-05");
  });
});

describe("the Costs page", () => {
  it("shows the days, the month, the herds, the machines and silage", async () => {
    draw(<Costs />);
    const days = await screen.findByTestId("cost-days");
    const cells = within(days).getAllByRole("row");
    // header + 2 days + 1 month
    expect(cells).toHaveLength(4);
    expect(within(days).getAllByText("35.00").length).toBeGreaterThan(0);
    // A day with no animals has no figure.
    expect(within(cells[2]).getByText("—", { selector: "[data-cell='per-animal']" })).toBeTruthy();
    expect(within(await screen.findByTestId("cost-herds")).getByText("12.50")).toBeTruthy();
    expect(within(screen.getByTestId("cost-machines")).getByText("Tractor 1")).toBeTruthy();
    expect(within(screen.getByTestId("cost-silage")).getByText("4.50")).toBeTruthy();
    const [method, args] = call.mock.calls.find(([m]) => String(m).endsWith("cost_per_animal"))!;
    expect(method).toContain("costing.cost_per_animal.cost_per_animal");
    expect((args as { from_date: string }).from_date.endsWith("-01")).toBe(true);
  });

  it("labels feed that came from tracker history, and only that", async () => {
    history = true;
    draw(<Costs />);
    const days = await screen.findByTestId("cost-days");
    const rows = within(days).getAllByRole("row");
    expect(within(rows[1]).getByText("from tracker history", { selector: "[data-cell='feed-history']" })).toBeTruthy();
    expect(within(rows[2]).queryByText("from tracker history")).toBeNull();
    expect(within(screen.getByTestId("cost-herds")).getByText("1 day from tracker history")).toBeTruthy();
    expect(screen.getByText(/of this month's feed is from tracker history/)).toBeTruthy();
  });

  it("says nothing of history when there is none", async () => {
    draw(<Costs />);
    await screen.findByTestId("cost-days");
    expect(document.querySelector("[data-cell='feed-history'], [data-cell='herd-history']")).toBeNull();
    expect(screen.queryByText(/of this month's feed is from tracker history/)).toBeNull();
  });

  it("leaves the production panels out without production", async () => {
    production = false;
    draw(<Costs />);
    await screen.findByTestId("cost-days");
    expect(screen.queryByTestId("cost-machines")).toBeNull();
    expect(screen.queryByText("Silage cost per kg")).toBeNull();
  });
});

describe("the Daily Labour screen", () => {
  it("fills every category, totals from the rates and saves the day", async () => {
    draw(<Labour />);
    const table = await screen.findByTestId("labour-rows");
    // "Other" was missing from the answer and is added with its default rate.
    expect(within(table).getByText("Other")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Feedlot workers workers"), { target: { value: "6" } });
    fireEvent.change(screen.getByLabelText("Other workers"), { target: { value: "1" } });
    expect(within(table).getByText("2,750", { selector: "[data-cell='total']" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /save the day's labour/i }));
    await waitFor(() =>
      expect(call.mock.calls.some(([m]) => String(m).endsWith("save_daily_labour"))).toBe(true),
    );
    const [, args] = call.mock.calls.find(([m]) => String(m).endsWith("save_daily_labour"))!;
    const payload = (args as { payload: { rows: Array<{ category: string; workers: number }> } }).payload;
    expect(payload.rows.find((r) => r.category === "Feedlot workers")?.workers).toBe(6);
    expect(payload.rows).toHaveLength(3);
  });
});

describe("the Dashboard panel", () => {
  it("shows this month's cost per animal", async () => {
    draw(<CostPanel />);
    const panel = await screen.findByTestId("cost-panel");
    await waitFor(() => expect(within(panel).getAllByText("35.00").length).toBe(2));
    expect(within(panel).getByText("On 2026-11-01")).toBeTruthy();
  });

  it("says nothing to a user who may not read costs", async () => {
    refuse = true;
    const { container } = draw(<CostPanel />);
    await waitFor(() => expect(call).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector("[data-testid='cost-panel']")).toBeNull());
  });
});
