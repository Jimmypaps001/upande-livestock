import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The beef screens, rendered against the backend contract's shapes.
 */

const performance = {
  herd: "Finishing 1",
  herd_class: "Fattening",
  target_adg_kg: 0.9,
  period_days: 90,
  summary: { head_count: 3, avg_weight_kg: 312.4, avg_period_adg: 0.85 },
  rows: [
    { animal: "B-UNRANKED", label: "B-UNRANKED", latest_weight_kg: 280, latest_weight_date: "2026-09-01",
      days_since_weighing: 56, period_adg: null, herd_adg: null, lifetime_adg: null, rank: null, below_target: null },
    { animal: "B-SLOW", label: "B-SLOW", latest_weight_kg: 300, latest_weight_date: "2026-10-01",
      days_since_weighing: 26, period_adg: 0.61, herd_adg: 0.85, lifetime_adg: 0.7, rank: 2, below_target: true },
    { animal: "B-FAST", label: "B-FAST", latest_weight_kg: 345, latest_weight_date: "2026-10-01",
      days_since_weighing: 26, period_adg: 1.1, herd_adg: 0.85, lifetime_adg: 1.0, rank: 1, below_target: false },
  ],
};

const payloads: Record<string, unknown> = {
  get_bull_performance: performance,
  list_performance_herds: [{ herd: "Finishing 1", herd_class: "Fattening", head_count: 3 }],
  get_livestock_workspace_stats: {
    kpis: {},
    herds: [],
    beef: {
      herds: [{ herd: "Finishing 1", herd_class: "Fattening", head_count: 3, avg_weight_kg: 312.4, avg_adg_kg: 0.85 }],
      weighings_overdue: 4,
      band_moves_due: 2,
      ready_for_exit: 1,
    },
  },
  herd_rations: {
    ok: true,
    herds: [
      { herd: "Finishing 1", herd_class: "Fattening", min_weight_kg: 250, max_weight_kg: 350,
        target_adg_kg: 0.9, weigh_monthly: 1 },
      { herd: "Bulls", herd_class: "Breeding", min_weight_kg: 0, max_weight_kg: 0,
        target_adg_kg: 0, weigh_monthly: 1 },
    ],
    feeds: [],
  },
  save_band_ladder: { ok: true, bands: [] },
  update_herd: { ok: true, herd: "Finishing 1", herd_class: "Fattening", min_weight_kg: 250, max_weight_kg: 360,
    target_adg_kg: 0.9, weigh_monthly: 1 },
  get_cull_board: { ok: true, animals: [] },
  disposal_options: { ok: true, customers: ["Butcher Ltd"] },
  record_disposal: { ok: true, name: "DISP-1", sale_price: 117420, warnings: [] },
};

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  void args;
  const key = Object.keys(payloads)
    .filter((k) => (method || "").includes(k))
    .sort((a, b) => b.length - a.length)[0];
  return key ? payloads[key] : { ok: true, animals: [], rows: [], herds: [] };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

// The feed projection has its own tests; here it is only the neighbour.
vi.mock("@/pages/Projection", () => ({ ProjectionBody: () => null }));

const { Performance } = await import("@/pages/Performance");
const { Herds } = await import("@/pages/Herds");
const { HerdBandFields } = await import("@/components/herds/HerdBandFields");
const { Dashboard } = await import("@/pages/Dashboard");

const wrap = (ui: React.ReactNode) =>
  render(
    <TooltipProvider>
      <ToastProvider>{ui}</ToastProvider>
    </TooltipProvider>,
  );

describe("Bull Performance page", () => {
  it("ranks animals, shows ADG with 2 decimals, flags below-target and puts unranked last", async () => {
    wrap(<Performance />);
    await waitFor(() => expect(screen.getByText("B-FAST")).toBeTruthy());

    const tags = screen.getAllByRole("row").slice(1, 4).map((r) => r.querySelector("td:nth-child(2)")?.textContent);
    expect(tags).toEqual(["B-FAST", "B-SLOW", "B-UNRANKED"]);

    expect(screen.getByText("1.10 kg/day")).toBeTruthy();
    expect(screen.getByText("Not enough weighings")).toBeTruthy();

    const slow = screen.getByText("B-SLOW").closest("tr")!;
    expect(slow.getAttribute("data-below-target")).toBe("true");
    expect(screen.getByText("B-FAST").closest("tr")!.getAttribute("data-below-target")).toBeNull();
    expect(screen.getByText("B-UNRANKED").closest("tr")!.getAttribute("data-below-target")).toBeNull();
  });

  it("asks for the herd for the default 90-day period", async () => {
    call.mockClear();
    wrap(<Performance />);
    await waitFor(() => expect(call).toHaveBeenCalledWith(
      expect.stringContaining("get_bull_performance"),
      { herd: "Finishing 1", period_days: 90 },
    ));
  });
});

describe("herd band fields", () => {
  const base = { herd_class: "Other" as const, min_weight_kg: "", max_weight_kg: "", target_adg_kg: "", weigh_monthly: false };

  it("are hidden for a class with no band", () => {
    wrap(<HerdBandFields idPrefix="t" value={base} onChange={() => {}} />);
    expect(screen.queryByLabelText("Band from (kg)")).toBeNull();
  });

  it.each(["Fattening", "Calf"] as const)("are shown for %s", (c) => {
    wrap(<HerdBandFields idPrefix="t" value={{ ...base, herd_class: c }} onChange={() => {}} />);
    expect(screen.getByLabelText("Band from (kg)")).toBeTruthy();
    expect(screen.getByLabelText("Band up to (kg)")).toBeTruthy();
    expect(screen.getByLabelText("Target gain (kg/day)")).toBeTruthy();
  });
});

describe("Herds editor", () => {
  it("saves the edited band through update_herd and shows a server refusal unchanged", async () => {
    wrap(<Herds />);
    fireEvent.click(await screen.findByLabelText("Which herd"));
    fireEvent.click(await screen.findByRole("option", { name: "Finishing 1" }));
    const max = await screen.findByLabelText("Band up to (kg)", { selector: "#eh-max" });
    fireEvent.change(max, { target: { value: "360" } });
    fireEvent.click(screen.getByText("Save the herd"));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        expect.stringContaining("update_herd"),
        expect.objectContaining({ herd: "Finishing 1", herd_class: "Fattening", min_weight_kg: 250, max_weight_kg: 360, target_adg_kg: 0.9 }),
      ),
    );
  });
});

describe("Edit bands ladder editor", () => {
  it("lists the Fattening herds and saves every rung in one call", async () => {
    call.mockClear();
    wrap(<Herds />);
    const top = await screen.findByLabelText("Finishing 1 up to (kg)");
    expect(screen.queryByLabelText("Bulls up to (kg)")).toBeNull();
    fireEvent.change(top, { target: { value: "270" } });
    fireEvent.click(screen.getByText("Save the bands"));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        expect.stringContaining("save_band_ladder"),
        { bands: [{ herd: "Finishing 1", min_weight_kg: 250, max_weight_kg: 270, target_adg_kg: 0.9 }] },
      ),
    );
  });
});

describe("Exit from Bull Performance", () => {
  async function openExit() {
    wrap(<Performance />);
    fireEvent.click(await screen.findByLabelText("Exit B-FAST"));
    return screen.findByText("Exit B-FAST");
  }

  it("sends a one-step sale to record_disposal and previews the amount", async () => {
    call.mockClear();
    await openExit();
    fireEvent.click(await screen.findByLabelText("Customer"));
    fireEvent.click(await screen.findByRole("option", { name: "Butcher Ltd" }));
    fireEvent.change(screen.getByLabelText("Price per kg"), { target: { value: "340" } });
    expect(screen.getByTestId("exit-amount").textContent).toContain("117,300");
    fireEvent.click(screen.getByText("Record the sale"));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        expect.stringContaining("record_disposal"),
        { payload: expect.objectContaining({
            animal: "B-FAST", disposal_type: "Sold", customer: "Butcher Ltd", price_per_kg: 340 }) },
      ),
    );
  });

  it("will not record a sale without a price per kg", async () => {
    call.mockClear();
    await openExit();
    fireEvent.click(screen.getByText("Record the sale"));
    expect(await screen.findByText(/price per kg/i, { selector: "[role=alert] *, [role=alert]" })).toBeTruthy();
    expect(call).not.toHaveBeenCalledWith(expect.stringContaining("record_disposal"), expect.anything());
  });

  it("shows the withdrawal warning the server returns", async () => {
    const prev = payloads.record_disposal;
    payloads.record_disposal = { ok: true, name: "DISP-2", warnings: ["Inside the withdrawal period until 2026-11-02."] };
    try {
      await openExit();
      fireEvent.click(screen.getByLabelText("Leaving as"));
      fireEvent.click(await screen.findByRole("option", { name: "Slaughtered" }));
      fireEvent.click(screen.getByText("Record the slaughter"));
      expect(await screen.findByText(/withdrawal period until/)).toBeTruthy();
    } finally {
      payloads.record_disposal = prev;
    }
  });
});

describe("Herds editor refusal", () => {
  it("shows the server's refusal verbatim", async () => {
    const msg = "Band 250-360 kg overlaps Finishing 2 (340-450 kg).";
    const prev = payloads.update_herd;
    payloads.update_herd = { error: msg };
    try {
      wrap(<Herds />);
      fireEvent.click(await screen.findByLabelText("Which herd"));
      fireEvent.click(await screen.findByRole("option", { name: "Finishing 1" }));
      fireEvent.click(await screen.findByText("Save the herd"));
      expect(await screen.findByText(msg)).toBeTruthy();
    } finally {
      payloads.update_herd = prev;
    }
  });
});

describe("Performance summary row and stale responses", () => {
  it("renders the herd summary as the table's footer row", async () => {
    wrap(<Performance />);
    const row = await screen.findByTestId("herd-summary-row");
    expect(row.textContent).toContain("3 head");
    expect(row.textContent).toContain("312 kg");
    expect(row.textContent).toContain("0.85 kg/day");
  });

  it("lets only the newest request write when the period changes quickly", async () => {
    let release!: (v: unknown) => void;
    const slow = new Promise((r) => { release = r; });
    const original = call.getMockImplementation()!;
    call.mockImplementation(async (method?: string, args?: Record<string, unknown>) => {
      if ((method || "").includes("get_bull_performance")) {
        if (args?.period_days === 90) return slow; // the first, slow request
        return { ...performance, period_days: 30, summary: { ...performance.summary, head_count: 7 } };
      }
      return original(method, args);
    });
    try {
      wrap(<Performance />);
      fireEvent.click(await screen.findByLabelText("Period"));
      fireEvent.click(await screen.findByRole("option", { name: "Last 30 days" }));
      await waitFor(() =>
        expect(screen.getByTestId("herd-summary-row").textContent).toContain("7 head"));
      release({ ...performance, summary: { ...performance.summary, head_count: 3 } });
      await new Promise((r) => setTimeout(r, 20));
      expect(screen.getByTestId("herd-summary-row").textContent).toContain("7 head");
    } finally {
      call.mockImplementation(original);
    }
  });
});

describe("Dashboard beef tiles", () => {
  it("shows the herd tile and the three work counts", async () => {
    wrap(<Dashboard />);
    await waitFor(() => expect(screen.getByText("Finishing 1")).toBeTruthy());
    expect(screen.getByText("Weighings overdue")).toBeTruthy();
    expect(screen.getByText("312 kg")).toBeTruthy();
    const overdue = screen.getByText("Weighings overdue").parentElement!;
    expect(overdue.textContent).toContain("4");
  });
});
