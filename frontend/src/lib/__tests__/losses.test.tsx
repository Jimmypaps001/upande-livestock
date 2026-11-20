import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LossCard } from "@/components/losses/LossCard";
import { RecordLossDialog } from "@/components/losses/RecordLossDialog";
import { Claims } from "@/pages/Claims";
import { canEditScenarios, trailSteps, type LossScenario, type LossTrail } from "@/lib/losses";
import * as api from "@/lib/losses";

vi.mock("@/lib/losses", async (orig) => {
  const real = await orig<typeof import("@/lib/losses")>();
  return {
    ...real,
    getLossScenarios: vi.fn(),
    recordLoss: vi.fn(),
    getLossTrail: vi.fn(),
    getLossClaims: vi.fn(),
  };
});

const THEFT: LossScenario = {
  name: "Theft",
  scenario_name: "Theft",
  active: 1,
  trigger: "Theft",
  outcome: "Write off",
  description: null,
  claim_insurance: 1,
  incident_type: "Theft",
  loss_treatment: "Total Loss",
  notify_roles: null,
  required_documents: [{ document_name: "Police abstract", mandatory: 1 }],
};
const CULL: LossScenario = {
  ...THEFT,
  name: "Cull",
  scenario_name: "Low production cull",
  trigger: "Low production",
  outcome: "Sell live",
  claim_insurance: 0,
  incident_type: null,
  loss_treatment: null,
  required_documents: [],
};

const TRAIL: LossTrail = {
  name: "LOSS-1",
  animal: "COW 1",
  scenario: "Injury - salvage slaughter",
  trigger: "Injury",
  outcome: "Sell for slaughter",
  incident_date: "2026-11-18",
  notes: null,
  status: "Awaiting claim",
  claim: {
    name: "INS-CLM-1",
    status: "Draft",
    amount_claimed: 1000,
    amount_approved: null,
    amount_received: null,
    outstanding_amount: null,
    missing_documents: ["Vet report"],
  },
  claim_note: null,
  disposal: null,
  waiting_for: "COW 1 cannot be sold yet: insurance claim INS-CLM-1 is Draft.",
  requirement: "Claim recorded",
};

describe("record a loss", () => {
  beforeEach(() => {
    vi.mocked(api.getLossScenarios).mockResolvedValue({
      ok: true,
      scenarios: [THEFT, CULL],
      requirement: "Claim recorded",
      incident_types: [],
    } as never);
  });

  it("shows the chosen scenario's checklist and sends the loss", async () => {
    vi.mocked(api.recordLoss).mockResolvedValue({ ok: true, name: "LOSS-9", claim: "INS-CLM-9", claim_status: "Draft" } as never);
    const onRecorded = vi.fn();
    render(<RecordLossDialog open onOpenChange={() => {}} animal="COW 1" onRecorded={onRecorded} />);
    await screen.findByText("Low production cull");
    expect(screen.queryByText(/Police abstract/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "Theft" } });
    expect(screen.getByText(/Police abstract \(required\)/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Incident date"), { target: { value: "2026-11-18" } });
    fireEvent.click(screen.getByRole("button", { name: "Record loss" }));
    await waitFor(() => expect(onRecorded).toHaveBeenCalled());
    expect(api.recordLoss).toHaveBeenCalledWith(
      expect.objectContaining({ animal: "COW 1", scenario: "Theft", incident_date: "2026-11-18", documents: [] }),
    );
    expect(await screen.findByText(/Claim INS-CLM-9 raised/)).toBeTruthy();
  });

  it("asks for a buyer only when the scenario sells", async () => {
    render(<RecordLossDialog open onOpenChange={() => {}} animal="COW 1" />);
    await screen.findByText("Low production cull");
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "Cull" } });
    expect(screen.getByLabelText("Sale price")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "Theft" } });
    expect(screen.queryByLabelText("Sale price")).toBeNull();
  });

  it("shows the server's refusal and the reason a sale is held", async () => {
    vi.mocked(api.recordLoss).mockResolvedValueOnce({ error: "COW 1 already has a loss in progress (LOSS-1)." } as never);
    render(<RecordLossDialog open onOpenChange={() => {}} animal="COW 1" />);
    await screen.findByText("Theft");
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "Theft" } });
    fireEvent.click(screen.getByRole("button", { name: "Record loss" }));
    expect(await screen.findByText(/already has a loss/)).toBeTruthy();
  });
});

describe("loss trail", () => {
  it("walks incident, claim, disposal, invoice and settlement", () => {
    const labels = trailSteps(TRAIL).map((s) => s.label);
    expect(labels).toEqual(["Incident", "Claim", "Disposal", "Invoice", "Settlement"]);
    expect(trailSteps(TRAIL)[1].done).toBe(false);
    expect(trailSteps({ ...TRAIL, outcome: "Write off", claim: null }).map((s) => s.label)).toEqual([
      "Incident",
      "Disposal",
    ]);
  });

  it("the card shows the trail and what the sale is waiting for", async () => {
    vi.mocked(api.getLossTrail).mockResolvedValue({ ok: true, losses: [TRAIL], requirement: "Claim recorded", cover: "insured" } as never);
    render(<LossCard animal="COW 1" status="Active" />);
    expect(await screen.findByText(/INS-CLM-1 · Draft/)).toBeTruthy();
    expect(screen.getByText(/cannot be sold yet/)).toBeTruthy();
    expect(screen.getByText(/Still to attach: Vet report/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Record a loss" })).toBeTruthy();
  });

  it("an animal that has left offers no new loss", async () => {
    vi.mocked(api.getLossTrail).mockResolvedValue({ ok: true, losses: [TRAIL], requirement: "Claim recorded", cover: "none" } as never);
    render(<LossCard animal="COW 1" status="Dead" />);
    await screen.findAllByText(/INS-CLM-1/);
    expect(screen.queryByRole("button", { name: "Record a loss" })).toBeNull();
  });
});

describe("claims page and scenario rights", () => {
  it("lists claims and filters by status", async () => {
    vi.mocked(api.getLossClaims).mockResolvedValue({
      ok: true,
      requirement: "Insurer approved",
      claims: [
        { name: "LOSS-1", animal: "COW 1", animal_name: "Daisy", scenario: "Theft", incident_date: "2026-11-01", claim: "INS-CLM-1", claim_status: "Draft", status: "Awaiting claim", disposal: null, sales_invoice: null, missing_documents: "Police abstract" },
        { name: "LOSS-2", animal: "COW 2", animal_name: "Bella", scenario: "Theft", incident_date: "2026-11-02", claim: "INS-CLM-2", claim_status: "Approved", status: "Closed", disposal: "D", sales_invoice: null, missing_documents: null, amount_approved: 5000 },
      ],
    } as never);
    render(
      <TooltipProvider>
        <Claims />
      </TooltipProvider>,
    );
    expect(await screen.findByText("Daisy")).toBeTruthy();
    expect(screen.getByText("Bella")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approved" }));
    expect(screen.queryByText("Daisy")).toBeNull();
    expect(screen.getByText("Bella")).toBeTruthy();
  });

  it("scenarios are edited by managers only", () => {
    expect(canEditScenarios(["Livestock Manager"])).toBe(true);
    expect(canEditScenarios(["System Manager"])).toBe(true);
    expect(canEditScenarios(["Accounts User", "Livestock Vet"])).toBe(false);
  });
});
