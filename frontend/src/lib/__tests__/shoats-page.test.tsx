import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The Shoats desk page, rendered against the endpoint shapes of the design file.
 */

const labels = { females: "Ewes", males: "Rams", young: "Lambs", others: "Others" };
const labelsGoat = { females: "Does", males: "Bucks", young: "Kids", others: "Others" };
const herd = (name: string, species: string, head: number[], extra: object = {}) => ({
  name, label: name, species, breed: species === "Sheep" ? "Dorper" : "Boer", paddock: "Paddock A2 - MUT",
  labels: species === "Sheep" ? labels : labelsGoat,
  head: { females: head[0], males: head[1], young: head[2], others: head[3], total: head.reduce((a, b) => a + b, 0) },
  live_weight_kg: 2313.6, avg_weight_kg: 27.5, weight_date: "2026-10-22", weight_basis: "class samples",
  withdrawal_until: null, in_withdrawal: false, last_count_date: "2026-10-15", has_ration: true, cost_center: "",
  next_due: { mating: "HCE-1", expected_birth_date: "2027-03-18", days_to_due: 140, females_served: 31 },
  mating_status: "Pending", ...extra,
});
const dorper = herd("Dorper Flock", "Sheep", [51, 8, 48, 0], { in_withdrawal: true, withdrawal_until: "2026-11-06" });
const boer = herd("Boer Goat Herd", "Goat", [37, 4, 43, 0], { live_weight_kg: 0, weight_basis: "none", avg_weight_kg: null });

const herds = {
  ok: true, today: "2026-10-29", herds: [dorper, boer], warnings: [],
  totals: {
    Sheep: { herds: 1, head: 107, live_weight_kg: 4983, avg_weight_kg: 46.6 },
    Goat: { herds: 1, head: 84, live_weight_kg: 0, avg_weight_kg: null },
    Shoats: { herds: 2, head: 191, live_weight_kg: 4983, avg_weight_kg: 26.1 },
  },
};
const ev = (name: string, type: string, rest: object) => ({
  name, event_date: "2026-10-15", event_type: type, females: 0, males: 0, young: 0, others: 0, born_dead: 0,
  change: 0, head_after: 107, cause: "", other_herd: "", paddock: "", reason: "", amount: 0, mating: "",
  variance: null, remarks: "", paired_event: "", ...rest,
});
const detail = (h: object) => ({
  ok: true, today: "2026-10-29", herd: h, warnings: [],
  ledger: [
    ev("E1", "Head Count", { females: 51, males: 8, young: 48, head_after: 107, variance: { females: -2, males: 0, young: 0, others: 0 } }),
    ev("E2", "Birth", { young: 22, born_dead: 2, change: 22, head_after: 109 }),
    ev("E3", "Death", { females: 1, change: -1, cause: "Predation", head_after: 108 }),
  ],
  weights: [{ name: "W1", sample_date: "2026-10-22", sample_class: "All", animals_weighed: 18, average_kg: 27.5, total_kg: 495 }],
  matings: [
    { name: "M1", herd: "Dorper Flock", species: "Sheep", mating_start: "2026-03-08", mating_end: "2026-04-07",
      expected_birth_date: "2026-09-04", days_to_due: -55, status: "Delivered", females_served: 40, males_in: 4,
      born_alive: 48, born_dead: 3, birth_rate_pct: 127.5, births: [] },
    { name: "M2", herd: "Dorper Flock", species: "Sheep", mating_start: "2026-09-29", mating_end: "2026-10-19",
      expected_birth_date: "2027-03-18", days_to_due: 140, status: "Pending", females_served: 41, males_in: 3,
      born_alive: 0, born_dead: 0, birth_rate_pct: null, births: [] },
  ],
  treatments: [{ name: "T1", treatment_date: "2026-10-23", treatment_type: "Deworming", product: "LSK-DEW-ALB",
    product_name: "Albendazole 10% Oral Drench (1 L)", dose_per_head: 0.0075, dose_uom: "Litre", number_treated: 107,
    quantity: 0.8, withdrawal_days: 14, withdrawal_end: "2026-11-06", diagnosis: "Routine drench", stock_entry: "MAT-1" }],
});
const options = {
  ok: true, today: "2026-10-29",
  event_types: ["Head Count", "Birth", "Death", "Purchase", "Sale", "Slaughter", "Transfer In", "Transfer Out", "Weaning", "Mating"]
    .map((name) => ({ name, direction: "none", needs: [] })),
  death_causes: ["Disease", "Predation"], treatment_types: ["Treatment", "Dipping", "Deworming", "Vaccination"],
  drug_store: "Drug Store - MUT", drugs: [{ item_code: "LSK-DEW-ALB", item_name: "Albendazole", uom: "Litre", qty: 8 }],
  herds: [],
};

const call = vi.hoisted(() => vi.fn());
call.mockImplementation(async (method?: string, args?: Record<string, unknown>) => {
  void args;
  const m = method || "";
  if (m.endsWith("shoat_herds.shoat_herds")) return herds;
  if (m.endsWith("shoat_herd.shoat_herd")) return detail(args?.herd === "Boer Goat Herd" ? boer : dorper);
  if (m.endsWith("shoat_options.shoat_options")) return options;
  if (m.endsWith("record_count_event.record_count_event")) return { ok: true, created: { count_event: "E9" }, warnings: ["Dorper Flock is in drug withdrawal until 2026-11-06"] };
  if (m.endsWith("record_weight_sample.record_weight_sample")) return { ok: true, created: { weight_sample: "W9" }, warnings: [] };
  if (m.includes("posting_day")) return { ok: true, today: "2026-10-29", backdating_open: false };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

import { Shoats } from "@/pages/Shoats";

function renderPage() {
  return render(
    <TooltipProvider>
      <ToastProvider>
        <Shoats />
      </ToastProvider>
    </TooltipProvider>,
  );
}

describe("Shoats page", () => {
  it("lists the herds with head by class, totals and live weight", async () => {
    renderPage();
    await screen.findByRole("button", { name: "Open Dorper Flock" });
    expect(screen.getByRole("button", { name: "Open Boer Goat Herd" })).toBeTruthy();
    expect(screen.getByText("191")).toBeTruthy();
    expect(screen.getByText("2,314 kg")).toBeTruthy();
    // a herd nobody has weighed says so instead of 0 kg
    expect(screen.getByText("No sample")).toBeTruthy();
    expect(screen.getByText("Withdrawal to 2026-11-06")).toBeTruthy();
  });

  it("opens the first herd's ledger with the variance of a head count", async () => {
    renderPage();
    await screen.findByText("Variance −2 ewes");
    expect(screen.getByText("Predation")).toBeTruthy();
    expect(screen.getByText("22 lambs, 2 born dead")).toBeTruthy();
    expect(screen.getByText("+22")).toBeTruthy();
    expect(screen.getByText("−1")).toBeTruthy();
    expect(screen.getByText(/Drug withdrawal runs until 2026-11-06/)).toBeTruthy();
  });

  it("shows weights, breeding and treatments on their tabs", async () => {
    renderPage();
    await screen.findByText("Variance −2 ewes");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Weights" }), { button: 0 });
    fireEvent.click(screen.getByRole("tab", { name: "Weights" }));
    expect(await screen.findByText("27.5 kg")).toBeTruthy();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Breeding" }), { button: 0 });
    fireEvent.click(screen.getByRole("tab", { name: "Breeding" }));
    expect(await screen.findByText("Delivered")).toBeTruthy();
    expect(screen.getByText("127.5% born per female")).toBeTruthy();
    expect(screen.getByText("Pending")).toBeTruthy();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Treatments" }), { button: 0 });
    fireEvent.click(screen.getByRole("tab", { name: "Treatments" }));
    expect(await screen.findByText("Albendazole 10% Oral Drench (1 L)")).toBeTruthy();
    expect(screen.getByText("Routine drench")).toBeTruthy();
  });

  it("switches herd and uses the goats' words", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Open Boer Goat Herd" }));
    await waitFor(() => expect(screen.getAllByText("Does").length).toBeGreaterThan(0));
    expect(call).toHaveBeenCalledWith(expect.stringContaining("shoat_herd.shoat_herd"), { herd: "Boer Goat Herd" });
  });

  it("records a weight sample and refreshes", async () => {
    renderPage();
    await screen.findByText("Variance −2 ewes");
    fireEvent.click(screen.getByRole("button", { name: "Weigh a sample" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText("Say how many animals were weighed.")).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText("Animals weighed"), { target: { value: "18" } });
    fireEvent.change(within(dialog).getByLabelText("Average weight (kg)"), { target: { value: "27.5" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        expect.stringContaining("record_weight_sample"),
        expect.objectContaining({ payload: expect.stringContaining('"animals_weighed":18') }),
      ),
    );
  });

  it("shows the server's warning after a movement is saved", async () => {
    renderPage();
    await screen.findByText("Variance −2 ewes");
    fireEvent.click(screen.getByRole("button", { name: "Record count or movement" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Ewes"), { target: { value: "2" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText(/in drug withdrawal until 2026-11-06/)).toBeTruthy();
  });
});
