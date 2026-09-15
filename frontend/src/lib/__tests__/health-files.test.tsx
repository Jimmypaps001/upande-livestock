import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The health file, from the screens' side.
 *
 * What is protected here is the hospital shape, because that is what the farm
 * asked for and what the old screens quietly prevented: a treatment goes into
 * the file she already has unless somebody deliberately starts another, and a
 * new file cannot be opened without saying what is wrong with her.
 */

const OPEN_CASE = {
  name: "HC-1",
  animal: "A001/16",
  animal_name: "ABIGEAL",
  current_herd: "Lactating group 1",
  case_status: "Under Treatment",
  opened_date: "2026-08-20",
  closed_date: null,
  presenting_symptoms: "Swollen left hind quarter",
  provisional_diagnosis: "Mastitis",
  confirmed_diagnosis: null,
  severity: "Moderate",
  duration_days: null,
  production_loss_kg: null,
  total_treatment_cost: null,
  vet_called: 0,
  vet_name: null,
  days_open: 11,
  treatments: 4,
  last_treatment_on: "2026-08-29",
  last_response: "Improving",
  open: true,
  concern: null,
};

const CLOSED_CASE = {
  ...OPEN_CASE,
  name: "HC-0",
  case_status: "Recovered",
  opened_date: "2026-03-02",
  closed_date: "2026-03-12",
  days_open: 10,
  open: false,
  concern: null,
};

const payloads: Record<string, unknown> = {
  health_overview: {
    ok: true,
    since: "2025-09-01",
    herd_size: 371,
    under_treatment: 0,
    share: 0,
    ward: [],
    worrying: [],
    months: [{ month: "2026-09", opened: 0, closed: 0 }],
    diagnoses: [],
    severity: [],
    herds: [],
    cost: { treatment: 0, lost_kg: 0, costed: 0, cases: 0 },
    concern_days: 21,
    stale_days: 7,
  },
  health_cases: {
    ok: true,
    from: "2025-09-15",
    to: "2026-09-15",
    cases: [OPEN_CASE, CLOSED_CASE],
    counts: { total: 2, open: 1, closed: 1, recovered: 1, died: 0, lost_kg: 0, cost: 0 },
    truncated: false,
    concern_days: 21,
    stale_days: 7,
    months: [],
  },
  case_for_animal: {
    ok: true,
    animal: "A001/16",
    open_case: { ...OPEN_CASE, days_open: 11, treatments: 4 },
    history: [],
    closed_count: 2,
  },
  health_options: {
    ok: true,
    animals: [
      { name: "A001/16", label: "A001/16", herd: "Lactating group 1", herd_label: "Lactating group 1" },
    ],
    carrying: [],
    diseases: ["Mastitis"],
    abortion_causes: [],
    appearances: [],
    hydrations: [],
    actions: [],
    case_statuses: [],
    severities: ["Mild", "Moderate"],
    routes: ["IM (Intramuscular)"],
    employee: "HR-EMP-00001",
  },
  open_health_cases: {
    ok: true,
    cases: [],
    drug_items: [{ value: "LSK-AB-OTC", label: "Oxytet · 40 Litre in store", qty: 40, uom: "Litre" }],
    routes: ["IM (Intramuscular)"],
    employee: "HR-EMP-00001",
  },
};

const call = vi.fn(async (method?: string) => {
  // Longest match wins: "open_health_cases" contains "health_cases", and a
  // first-match lookup would hand the drug picker the register's payload.
  const key = Object.keys(payloads)
    .filter((k) => (method || "").includes(k))
    .sort((a, b) => b.length - a.length)[0];
  return key ? payloads[key] : { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { HealthDashboard } = await import("@/pages/HealthDashboard");
const { HealthCases } = await import("@/pages/HealthCases");
const { Treatment } = await import("@/pages/Treatment");

const draw = (Page: React.ComponentType) =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <Page />
      </ToastProvider>
    </TooltipProvider>,
  );

describe("the health dashboard", () => {
  it("says the ward is empty rather than showing a blank list", async () => {
    draw(HealthDashboard);
    await waitFor(() =>
      expect(screen.getByText(/Nobody is under treatment/)).toBeTruthy(),
    );
  });
});

describe("the register", () => {
  it("separates files being treated from files that are shut", async () => {
    draw(HealthCases);
    await waitFor(() => expect(screen.getByText("Being treated (1)")).toBeTruthy());
    expect(screen.getByText("Closed (1)")).toBeTruthy();
  });

  it("counts what the window opened and what it closed, not just the total", async () => {
    // Both fall inside the default twelve-month window, and they are different
    // questions: one file was opened in it and a different one was closed in it.
    draw(HealthCases);
    await waitFor(() => expect(screen.getByText("Opened")).toBeTruthy());
    expect(screen.getByText("Closed")).toBeTruthy();
    expect(screen.getByText("Still open")).toBeTruthy();
  });
});

describe("treating an animal", () => {
  it("keeps the long animal list inside its own scroller", async () => {
    // Unbounded, it pushed the drug rows and the record button below the fold
    // and left the page scrolling past four hundred cows to reach them.
    draw(Treatment);
    await waitFor(() => expect(screen.getByText("Which animal")).toBeTruthy());
    const card = screen.getByText("Which animal").closest("div[class*='max-h-']");
    expect(card).toBeTruthy();
    expect((card as HTMLElement).className).toContain("overflow-hidden");
  });

  it("shows the file she already has instead of asking which case", async () => {
    draw(Treatment);
    await waitFor(() => expect(screen.getAllByText("A001/16").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByText("A001/16")[0]);
    await waitFor(() => expect(screen.getByText("Add to her open file")).toBeTruthy());
    expect(screen.getByText(/Open since 2026-08-20/)).toBeTruthy();
  });

  it("will not open a second file without saying what is wrong with her", async () => {
    draw(Treatment);
    await waitFor(() => expect(screen.getAllByText("A001/16").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByText("A001/16")[0]);
    await waitFor(() => expect(screen.getByText("Open a new file")).toBeTruthy());
    fireEvent.click(screen.getByText("Open a new file"));
    await waitFor(() =>
      expect(screen.getByText(/A new file needs a complaint/)).toBeTruthy(),
    );
  });
});
