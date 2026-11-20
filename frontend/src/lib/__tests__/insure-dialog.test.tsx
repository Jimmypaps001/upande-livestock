import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InsureDialog, canInsure } from "@/components/animals/InsureDialog";
import * as api from "@/lib/animals-api";

vi.mock("@/lib/animals-api");

describe("insuring an animal", () => {
  beforeEach(() => {
    vi.mocked(api.getCoverPolicies).mockResolvedValue({
      ok: true,
      available: true,
      policies: [
        { name: "INS-1", policy_number: "N-9", policy_type: "Theft", insurer_name: "Jubilee", start_date: "2026-01-01", end_date: "2026-12-31" },
      ],
    } as never);
  });

  it("is for Accounts and System Manager only", () => {
    expect(canInsure(["Accounts User"])).toBe(true);
    expect(canInsure(["Accounts Manager"])).toBe(true);
    expect(canInsure(["System Manager"])).toBe(true);
    expect(canInsure(["Livestock Manager", "Livestock Vet"])).toBe(false);
  });

  it("sends the chosen policy, sum and endorsement through insure_animal", async () => {
    vi.mocked(api.insureAnimal).mockResolvedValue({ ok: true, asset: "A-1" } as never);
    const onInsured = vi.fn();
    render(<InsureDialog open onOpenChange={() => {}} animal="COW 1" onInsured={onInsured} />);
    await screen.findByText(/N-9/);
    fireEvent.change(screen.getByLabelText("Policy"), { target: { value: "INS-1" } });
    fireEvent.change(screen.getByLabelText(/Sum insured/), { target: { value: "90000" } });
    fireEvent.change(screen.getByLabelText("Endorsement no."), { target: { value: "E1" } });
    fireEvent.click(screen.getByRole("button", { name: "Insure" }));
    await waitFor(() => expect(onInsured).toHaveBeenCalled());
    expect(api.insureAnimal).toHaveBeenCalledWith({
      animal: "COW 1", policy: "INS-1", sum_insured: 90000, effective_date: undefined, endorsement_no: "E1",
    });
  });

  it("shows the server's refusal", async () => {
    vi.mocked(api.insureAnimal).mockResolvedValue({ error: "Only Accounts can insure an animal." } as never);
    render(<InsureDialog open onOpenChange={() => {}} animal="COW 1" />);
    await screen.findByText(/N-9/);
    fireEvent.change(screen.getByLabelText("Policy"), { target: { value: "INS-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Insure" }));
    expect(await screen.findByText(/Only Accounts/)).toBeTruthy();
  });
});
