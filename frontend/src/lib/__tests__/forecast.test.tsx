import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/Toast";

const bull = (o: Record<string, unknown>) => ({
  animal: "A1", label: "A1", herd: "Fattening 1", latest_weight_kg: 400,
  latest_weight_date: "2026-10-01", forecast_adg: 1.1, adg_source: "own",
  ready_date: "2026-11-10", ready_week: "2026-11-09", ...o,
});

let unforecastable = 2;
const call = vi.fn(async (method?: string, args?: unknown) => {
  const m = method || "";
  if (m.endsWith("list_performance_herds")) return [{ herd: "Fattening 1", herd_class: "Fattening", head_count: 4 }];
  if (m.endsWith("get_output_forecast"))
    return {
      exit_weight_kg: 450, horizon_weeks: 12, unforecastable,
      weeks: [{ week_start: "2026-11-09", head: 3, kg: 1380.5 }],
      bulls: [
        bull({ animal: "A1", adg_source: "own" }),
        bull({ animal: "A2", adg_source: "herd" }),
        bull({ animal: "A3", adg_source: "herd_target" }),
        bull({ animal: "A4", adg_source: "farm_target" }),
      ],
    };
  if (m.endsWith("get_commitment_cover")) {
    const row = (week_start: string, status: string, carry: number) => ({
      week_start, ready_head: 1, ready_kg: 1, committed_head: 1, committed_kg: 0,
      carry_in_head: carry, available_head: 1, balance_head: 0, status,
    });
    return { weeks: [row("2026-11-02", "Gap", 0), row("2026-11-09", "Covered", 7), row("2026-11-16", "Surplus", 0), row("2026-11-23", "Idle", 0)] };
  }
  if (m.endsWith("save_buyer_commitment")) return (args as { payload: { head: number } }).payload.head === 99 ? { error: "Not enough bulls." } : { ok: true, name: "LBC-1" };
  if (m.endsWith("get_forecast_accuracy"))
    return { weeks: [{ week_start: "2026-10-05", snapshot_date: "2026-10-01", forecast_head: 4, actual_head: 5, forecast_kg: 1000, actual_kg: null, error_pct_head: 0.25, error_pct_kg: null },
      { week_start: "2026-10-12", snapshot_date: "2026-10-08", forecast_head: 5, actual_head: 4, forecast_kg: 1000, actual_kg: 900, error_pct_head: -0.2, error_pct_kg: -0.1 }] };
  if (m.endsWith("get_productivity_trend"))
    return {
      farm: [{ week_start: "2026-10-05", avg_adg: 1, head: 3, avg_weight: 400 }],
      series: [{ herd: "Fattening 1", target_adg_kg: 0.9, points: [{ week_start: "2026-10-05", avg_adg: 1, head: 3, avg_weight: 400 }, { week_start: "2026-10-12", avg_adg: 1.1, head: 3, avg_weight: 410 }] }],
    };
  return {};
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Forecast } = await import("@/pages/Forecast");
const { formatErrorPct, mondayOf, adgSourceLabel } = await import("@/lib/forecast");

function draw() {
  return render(
    <TooltipProvider>
      <ToastProvider>
        <Forecast />
      </ToastProvider>
    </TooltipProvider>,
  );
}
const open = (name: string) => fireEvent.mouseDown(screen.getByRole("tab", { name }));

describe("forecast helpers", () => {
  it("normalises any date to its Monday", () => {
    expect(mondayOf("2026-10-28")).toBe("2026-10-26");
    expect(mondayOf("2026-10-26")).toBe("2026-10-26");
    expect(mondayOf("2026-11-01")).toBe("2026-10-26");
  });
  it("formats signed percents and null", () => {
    expect(formatErrorPct(0.25)).toBe("+25.0%");
    expect(formatErrorPct(-0.1)).toBe("-10.0%");
    expect(formatErrorPct(null)).toBe("—");
    expect(adgSourceLabel("farm_target")).toBe("Farm target");
  });
});

describe("the forecast page", () => {
  beforeEach(() => {
    call.mockClear();
    unforecastable = 2;
  });

  it("shows weekly head and kg, the unforecastable note and ADG sources", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("3 head")).toBeTruthy());
    expect(screen.getByText("1,380.5 kg")).toBeTruthy();
    expect(screen.getByText("2 bulls can't be forecast yet")).toBeTruthy();
    for (const l of ["Own", "Herd average", "Herd target", "Farm target"]) expect(screen.getByText(l)).toBeTruthy();
  });

  it("omits the note when every bull can be forecast", async () => {
    unforecastable = 0;
    draw();
    await waitFor(() => expect(screen.getByText("3 head")).toBeTruthy());
    expect(screen.queryByText(/can't be forecast yet/)).toBeNull();
  });

  it("colours cover statuses, shows carry-in and leaves Idle neutral", async () => {
    draw();
    await waitFor(() => screen.getByText("3 head"));
    open("Cover");
    await waitFor(() => expect(screen.getByTestId("cover-rows")).toBeTruthy());
    expect(screen.getByText("Gap").className).toMatch(/critical/);
    expect(screen.getByText("Covered").className).toMatch(/moderate/);
    expect(screen.getByText("Surplus").className).toMatch(/muted/);
    const idle = screen.getByText("Idle");
    expect(idle.className).not.toMatch(/critical|moderate/);
    expect(screen.getByText("7 head")).toBeTruthy(); // carry-in
  });

  it("posts the commitment with the week as a Monday and shows an error verbatim", async () => {
    draw();
    await waitFor(() => screen.getByText("3 head"));
    open("Cover");
    await waitFor(() => screen.getByLabelText("Customer"));
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "Farmer Joe" } });
    fireEvent.change(screen.getByLabelText(/Week \(any day\)/), { target: { value: "2026-10-28" } });
    fireEvent.change(screen.getByLabelText("Head"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: /Add commitment/ }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        expect.stringMatching(/save_buyer_commitment$/),
        { payload: { customer: "Farmer Joe", week_start: "2026-10-26", head: 5 } },
      ),
    );
    fireEvent.change(screen.getByLabelText("Head"), { target: { value: "99" } });
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "Farmer Joe" } });
    fireEvent.change(screen.getByLabelText(/Week \(any day\)/), { target: { value: "2026-10-28" } });
    fireEvent.click(screen.getByRole("button", { name: /Add commitment/ }));
    await waitFor(() => expect(screen.getByText("Not enough bulls.")).toBeTruthy());
  });

  it("shows accuracy as signed percents and an em dash for null", async () => {
    draw();
    await waitFor(() => screen.getByText("3 head"));
    open("Accuracy");
    await waitFor(() => expect(screen.getByTestId("accuracy-rows")).toBeTruthy());
    expect(screen.getByText("+25.0%")).toBeTruthy();
    expect(screen.getByText("-20.0%")).toBeTruthy();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("draws a series per herd with its target line", async () => {
    draw();
    await waitFor(() => screen.getByText("3 head"));
    open("Trend");
    await waitFor(() => expect(screen.getAllByTestId("trend-series").length).toBe(2));
    expect(screen.getAllByTestId("target-line").length).toBe(1);
    expect(screen.getByText("Target 0.90 kg/day")).toBeTruthy();
  });
});
