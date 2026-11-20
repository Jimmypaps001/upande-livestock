import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const call = vi.fn();
vi.mock("@/lib/frappe", async (orig) => ({
  ...(await orig<typeof import("@/lib/frappe")>()),
  call: (...a: unknown[]) => call(...a),
}));

const { Sires: SiresPage } = await import("@/pages/Sires");
const { TooltipProvider } = await import("@/components/ui/tooltip");
const Sires = () => (
  <TooltipProvider>
    <SiresPage />
  </TooltipProvider>
);
const { sireProblem } = await import("@/lib/sires");

const row = (o = {}) => ({
  name: "NL900000001", sire_name: "Dolmen", code: "NL900000001", label: "Dolmen · NL900000001",
  sire_type: "Semen", semen_item: "4040030118", animal: "", sexed: 1, active: 1, ...o,
});

beforeEach(() => call.mockReset());

describe("Sires page", () => {
  it("lists sires with code, filters by type and search", async () => {
    call.mockResolvedValue({ ok: true, sires: [row(), row({ name: "Mazira", sire_name: "Mazira", code: "", sire_type: "Live bull", sexed: 0, active: 0 })] });
    render(<Sires />);
    expect(await screen.findByText("Dolmen")).toBeTruthy();
    expect(screen.getByText("NL900000001", { selector: "td" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Live bull" }));
    expect(screen.queryByText("Dolmen")).toBeNull();
    expect(screen.getByText("Mazira")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.change(screen.getByLabelText("Find a sire"), { target: { value: "nl9" } });
    expect(screen.queryByText("Mazira")).toBeNull();
  });

  it("adds a sire through save_sire", async () => {
    call.mockImplementation(async (m?: string) => ((m ?? "").includes("save_sire") ? { ok: true, name: "X" } : { ok: true, sires: [] }));
    render(<Sires />);
    fireEvent.click(await screen.findByRole("button", { name: /Add sire/ }));
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "Arcana" } });
    fireEvent.change(screen.getByLabelText("Code"), { target: { value: "14HO14768" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(call.mock.calls.some((c) => String(c[0]).includes("save_sire"))).toBe(true));
    const save = call.mock.calls.find((c) => String(c[0]).includes("save_sire"))!;
    expect(save[1].payload).toMatchObject({ sire_name: "Arcana", sire_code: "14HO14768", sire_type: "Semen", active: 1, sexed: 0 });
  });

  it("a live bull needs an animal; a name is always needed", () => {
    const base = { sire_name: "A", sire_code: "", sire_type: "Live bull" as const, semen_item: "", animal: "", sexed: false, active: true };
    expect(sireProblem(base)).toMatch(/animal/);
    expect(sireProblem({ ...base, sire_name: "" })).toMatch(/name/);
    expect(sireProblem({ ...base, sire_type: "Semen" })).toBeNull();
  });

  it("breed is picked from the Breed list; supplier is shown fetched, not typed", async () => {
    call.mockImplementation(async (m?: string) =>
      (m ?? "").includes("sire_items")
        ? { ok: true, items: [], suggested: null, group: "Dairy Others", breeds: ["Holstein Friesian", "Jersey"], supplier: "Genus ABS" }
        : { ok: true, sires: [row()] });
    render(<Sires />);
    fireEvent.click(await screen.findByLabelText("Edit Dolmen"));
    await waitFor(() => expect(screen.getByText("Genus ABS")).toBeTruthy());
    expect(screen.queryByLabelText("Supplier")).toBeNull();
    fireEvent.click(screen.getByLabelText("Breed"));
    expect(await screen.findByRole("option", { name: "Jersey" })).toBeTruthy();
  });
});
