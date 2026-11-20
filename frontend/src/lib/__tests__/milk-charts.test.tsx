import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { beforeEach, describe, expect, it, vi } from "vitest";

const asked = vi.hoisted(() => ({ list: [] as { m: string; a: Record<string, string> }[] }));
const call = vi.hoisted(() => vi.fn());
call.mockImplementation(async (m?: string, a?: Record<string, string>) => {
  asked.list.push({ m: m ?? "", a: a ?? {} });
  if ((m ?? "").includes("milk_by_herd"))
    return {
      ok: true,
      days: ["2026-11-01", "2026-11-02"],
      herds: [
        { herd: "Small", kg: [10, 12], per_cow: [5, 6], total_kg: 22 },
        { herd: "Big", kg: [100, 120], per_cow: [10, 12], total_kg: 220 },
      ],
    };
  if ((m ?? "").includes("quality_trend"))
    return {
      ok: true,
      tests: [
        { name: "A", date: "2026-11-01", shift: "Morning", result: "Pass", fat: 3.8, protein: 3.2, snf: 8.5, ph: 6.7, tta: null, freezing_point: null, aflatoxin: null },
        { name: "B", date: "2026-11-02", shift: "Morning", result: "Fail", fat: 3.1, protein: 3.0, snf: 8.0, ph: null, tta: null, freezing_point: null, aflatoxin: null },
      ],
    };
  return { ok: true };
});
vi.mock("@/lib/frappe", async () => ({ ...(await vi.importActual<object>("@/lib/frappe")), call }));

const { orderHerds, periodRange, colourFor, SERIES_COLOURS } = await import("@/lib/milk-charts");
const { QUALITY_ROLE, viewAllowed } = await import("@/lib/roles");
const { YieldByHerdCard, QualityTrendCard } = await import("@/components/milking/MilkCharts");

beforeEach(() => { asked.list.length = 0; });

describe("chart helpers", () => {
  it("a period covers n days including today", () => {
    expect(periodRange(14, new Date(2026, 10, 20))).toEqual({ from_date: "2026-11-07", to_date: "2026-11-20" });
  });
  it("biggest herd first, colours cycle", () => {
    expect(orderHerds([{ herd: "S", kg: [], per_cow: [], total_kg: 1 }, { herd: "B", kg: [], per_cow: [], total_kg: 9 }])[0].herd).toBe("B");
    expect(colourFor(SERIES_COLOURS.length)).toBe(SERIES_COLOURS[0]);
  });
  it("Livestock Quality alone sees the quality page; a manager sees every page", () => {
    expect(viewAllowed("quality", [QUALITY_ROLE])).toBe(true);
    expect(viewAllowed("quality", ["Livestock Manager"])).toBe(true);
    expect(viewAllowed("milking", [QUALITY_ROLE])).toBe(false);
  });
});

describe("yield by herd", () => {
  it("draws one legend entry per herd and refetches on a new period", async () => {
    render(<TooltipProvider><YieldByHerdCard /></TooltipProvider>);
    await screen.findByLabelText("Herds");
    expect(screen.getByText("Big")).toBeTruthy();
    expect(screen.getByText("Small")).toBeTruthy();
    fireEvent.click(screen.getByText("90 days"));
    await waitFor(() => expect(asked.list.filter((c) => c.m.includes("milk_by_herd")).length).toBe(2));
    const last = asked.list[asked.list.length - 1].a;
    expect(last.to_date > last.from_date).toBe(true);
    fireEvent.click(screen.getByText("Per cow"));
    expect(screen.getByText("Per cow").getAttribute("aria-pressed")).toBe("true");
  });
});

describe("quality trend", () => {
  it("marks each batch pass or fail", async () => {
    render(<TooltipProvider><QualityTrendCard /></TooltipProvider>);
    await screen.findByTestId("mark-fail");
    expect(screen.getAllByTestId("mark-pass")).toHaveLength(1);
    expect(screen.getAllByTestId("mark-fail")).toHaveLength(1);
  });
});
