import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const family = {
  ok: true,
  id: "A1",
  parents: {
    dam: { id: "D1", name: "DAISY", tag: null, sex: "Female", dob: null, status: "Active", active: true, photo: null, thumb: null, onRecord: true },
    sire: { id: null, name: "NORDIC RED 4471", tag: null, sex: "Male", dob: null, status: null, active: false, photo: null, thumb: null, onRecord: false },
  },
  offspring: [
    { id: "C1", name: "CALF ONE", tag: null, sex: "Female", dob: "2026-01-02", status: "Active", active: true, photo: null, thumb: null, onRecord: true },
    { id: "C2", name: "CALF TWO", tag: null, sex: "Male", dob: "2025-01-02", status: "Sold", active: false, photo: null, thumb: null, onRecord: true },
  ],
  sons: 1,
  daughters: 1,
  bred: null,
};

const call = vi.fn();
vi.mock("@/lib/frappe", async (orig) => ({ ...(await orig<typeof import("@/lib/frappe")>()), call: (...a: unknown[]) => call(...a) }));

const { FamilyCard } = await import("@/components/animals/FamilyCard");

describe("FamilyCard", () => {
  beforeEach(() => {
    call.mockReset();
    call.mockResolvedValue(family);
  });

  it("shows dam, a sire written in by name, and every calf with what became of the sold one", async () => {
    render(<FamilyCard animal="A1" onOpen={() => {}} />);
    await waitFor(() => expect(screen.getByText("DAISY")).toBeTruthy());
    expect(screen.getByText("NORDIC RED 4471")).toBeTruthy();
    expect(screen.getByText(/2 calves \(1 bull, 1 heifer\)/)).toBeTruthy();
    expect(screen.getByText("Sold")).toBeTruthy();
    expect((screen.getByText("NORDIC RED 4471") as HTMLButtonElement).disabled).toBe(true);
  });

  it("opens a relative who is still on the farm, not a sold one", async () => {
    const onOpen = vi.fn();
    render(<FamilyCard animal="A1" onOpen={onOpen} />);
    await waitFor(() => screen.getByText("DAISY"));
    fireEvent.click(screen.getByText("DAISY"));
    expect(onOpen).toHaveBeenCalledWith("D1");
    fireEvent.click(screen.getByText("CALF TWO"));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("draws nothing when the server refuses", async () => {
    call.mockResolvedValue({ error: "no" });
    const { container } = render(<FamilyCard animal="A1" onOpen={() => {}} />);
    await waitFor(() => expect(call).toHaveBeenCalled());
    await waitFor(() => expect(container.textContent).toBe(""));
  });
});
