import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const call = vi.fn();
vi.mock("@/lib/frappe", async (orig) => ({
  ...(await orig<typeof import("@/lib/frappe")>()),
  call: (...a: unknown[]) => call(...a),
}));

const { TooltipProvider } = await import("@/components/ui/tooltip");
const { Vets: VetsPage } = await import("@/pages/Vets");
const Vets = () => (
  <TooltipProvider>
    <VetsPage />
  </TooltipProvider>
);
const { AddVetDialog } = await import("@/components/vets/AddVetDialog");
const { vetProblem } = await import("@/lib/vets");

const kpis = {
  cases_opened: 7, cases_closed: 4, cases_open_now: 3, treatments: 12, check_ups: 5,
  inseminations: 8, pds_done: 6, services_confirmed: 5, services_pending: 1,
  pregnancy_rate: 62.5, avg_days_to_close: 4.5, drug_cost: 1200, last_activity: "2026-11-18",
};
const vet = (over = {}) => ({
  value: "VET-0001", label: "Jane Kamau", vet: "VET-0001", vet_name: "Jane Kamau", type: "Internal",
  detail: "Internal", enabled: 1, initials: "JK", image: "", phone: "0711111111", email: "",
  employee: "EMP-1", supplier: "", practice_name: "", registration_number: "", qualification: "",
  licence_expiry: null, licence_expired: false, kpis, ...over,
});
const list = (vets: unknown[]) => ({ ok: true, period: "90d", from: "2026-08-23", to: "2026-11-20", vets });

beforeEach(() => {
  call.mockReset();
});

describe("Vets page", () => {
  it("shows a card of KPIs for each vet", async () => {
    call.mockResolvedValue(list([vet(), vet({ vet: "VET-0002", value: "VET-0002", vet_name: "Peter Oloo", type: "External", practice_name: "Rift Vets", kpis: { ...kpis, inseminations: 0, pregnancy_rate: null } })]));
    render(<Vets />);
    expect(await screen.findByText("Jane Kamau")).toBeTruthy();
    expect(screen.getAllByTestId("vet-card")).toHaveLength(2);
    expect(screen.getByText("62.5%")).toBeTruthy();
    expect(screen.getAllByText("2026-11-18")).toHaveLength(2);
    expect(call.mock.calls[0][0]).toContain("vets_list");
    expect(call.mock.calls[0][1]).toEqual({ payload: { period: "90d" } });
  });

  it("filters by type and by search", async () => {
    call.mockResolvedValue(list([vet(), vet({ vet: "VET-0002", value: "VET-0002", vet_name: "Peter Oloo", type: "External" })]));
    render(<Vets />);
    await screen.findByText("Jane Kamau");
    fireEvent.click(screen.getByRole("button", { name: "External" }));
    expect(screen.queryByText("Jane Kamau")).toBeNull();
    expect(screen.getByText("Peter Oloo")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.change(screen.getByLabelText("Find a vet"), { target: { value: "jane" } });
    expect(screen.queryByText("Peter Oloo")).toBeNull();
    expect(screen.getByText("Jane Kamau")).toBeTruthy();
  });

  it("says so when there are no vets, and offers Add vet", async () => {
    call.mockResolvedValue(list([]));
    render(<Vets />);
    expect(await screen.findByText(/No vets yet/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Add vet/ })).toBeTruthy();
  });

  it("shows the server's refusal", async () => {
    call.mockResolvedValue({ error: "You are not permitted to read Livestock Vet." });
    render(<Vets />);
    expect(await screen.findByText(/not permitted to read/)).toBeTruthy();
  });

  it("refreshes the list after a vet is added", async () => {
    call.mockImplementation(async (method: string) => {
      if (method.includes("add_vet")) return { ok: true, vet: { value: "VET-0009", label: "Ann", type: "External", detail: "External" } };
      return list([]);
    });
    render(<Vets />);
    await screen.findByText(/No vets yet/);
    fireEvent.click(screen.getByRole("button", { name: /Add vet/ }));
    fireEvent.change(await screen.findByLabelText("Vet name"), { target: { value: "Ann" } });
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "0700" } });
    fireEvent.change(screen.getByLabelText(/Registration No/), { target: { value: "KVB-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save vet" }));
    await waitFor(() => expect(call.mock.calls.filter((c) => String(c[0]).includes("vets_list"))).toHaveLength(2));
  });
});

describe("AddVetDialog", () => {
  it("validates an external vet before calling the server", async () => {
    render(<AddVetDialog open onOpenChange={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Save vet" }));
    expect(await screen.findByText(/Vet Name is required/)).toBeTruthy();
    expect(call).not.toHaveBeenCalled();
  });

  it("sends the payload as typed and closes on success", async () => {
    call.mockResolvedValue({ ok: true, vet: { value: "VET-0010", label: "Ann" } });
    const onAdded = vi.fn();
    const onOpenChange = vi.fn();
    render(<AddVetDialog open onOpenChange={onOpenChange} onAdded={onAdded} />);
    fireEvent.change(screen.getByLabelText("Vet name"), { target: { value: "Ann" } });
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "0700" } });
    fireEvent.change(screen.getByLabelText(/Registration No/), { target: { value: "KVB-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save vet" }));
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    expect(call.mock.calls[0][0]).toContain("add_vet");
    expect(call.mock.calls[0][1]).toEqual({
      payload: { vet_type: "External", vet_name: "Ann", phone: "0700", registration_number: "KVB-1" },
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("shows the server's refusal and stays open", async () => {
    call.mockResolvedValue({ error: "VET-0001 is already the vet record for EMP-1." });
    const onOpenChange = vi.fn();
    render(<AddVetDialog open onOpenChange={onOpenChange} />);
    fireEvent.change(screen.getByLabelText("Vet name"), { target: { value: "Ann" } });
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "0700" } });
    fireEvent.change(screen.getByLabelText(/Registration No/), { target: { value: "K" } });
    fireEvent.click(screen.getByRole("button", { name: "Save vet" }));
    expect(await screen.findByText(/already the vet record/)).toBeTruthy();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("an internal vet needs an employee", () => {
    expect(vetProblem({ vet_type: "Internal" })).toMatch(/Employee/);
    expect(vetProblem({ vet_type: "Internal", employee: "EMP-1" })).toBeNull();
    expect(vetProblem({ vet_type: "External", vet_name: "A", phone: "1" })).toMatch(/Registration/);
  });
});
