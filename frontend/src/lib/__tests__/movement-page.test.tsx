import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Moving the animals that are due.
 *
 * TWO KINDS OF RULE, ONE LIST: a calf is due because she has been in her pen
 * long enough, a cow because she is far enough in calf. The herdsman at the
 * gate does not care which produced the row, so both arrive together and each
 * says why.
 *
 * And the selection is the screen. Everything due to one herd in a single tick,
 * then unpicked — because the person at the gate can see a cow this list
 * cannot.
 */

const suggestions = {
  ok: true,
  growth: [
    { animal: "A012/25", label: "NAserian (A012/25)", from_herd: "0-2", to_herd: "2-4",
      days_in_herd: 70, days_expected: 60, overdue: true, days_over: 10,
      reason: "70 days in the herd" },
    { animal: "A013/25", label: "SITA (A013/25)", from_herd: "0-2", to_herd: "2-4",
      days_in_herd: 61, days_expected: 60, overdue: false, days_over: 1,
      reason: "61 days in the herd" },
    { animal: "A039/26", label: "APIJA (A039/26)", from_herd: "Lactating group 1",
      to_herd: "LACTATION GROUP 2", days_in_herd: 124, days_expected: 120,
      overdue: false, days_over: 4, reason: "124 days in calf", days_to_calving: 146 },
  ],
  lactation: [],
  counts: {},
};

const call = vi.fn(async (method?: string): Promise<Record<string, unknown>> => {
  const m = method || "";
  if (m.includes("movement_suggestions")) return suggestions;
  if (m.includes("move_animals")) {
    return { ok: true, count: 2, herd: "2-4", emptied_from: ["0-2"], heads: 7 };
  }
  return { ok: true, animals: [], herds: [], calving_outcomes: [], employee: "HR-EMP-1" };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Movement } = await import("@/pages/Movement");

const draw = () =>
  render(
    <TooltipProvider>
      <Movement />
    </TooltipProvider>,
  );

describe("the movement page", () => {
  beforeEach(() => call.mockClear());

  it("groups them by where they are going", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("2-4")).toBeTruthy());
    expect(screen.getByText("LACTATION GROUP 2")).toBeTruthy();
  });

  it("says why each one is due, in the rule's own terms", async () => {
    // The calf's reason counts days in a pen; the cow's counts days in calf.
    draw();
    await waitFor(() => expect(screen.getByText(/70 days in the herd/)).toBeTruthy());
    expect(screen.getByText(/124 days in calf/)).toBeTruthy();
  });

  it("marks the late ones apart from the merely due", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("10 days late")).toBeTruthy());
    expect(screen.getAllByText("due").length).toBeGreaterThan(0);
  });

  it("takes everything due to one herd in a single tick", async () => {
    draw();
    const all = await screen.findByRole("button", { name: /Pick every animal due into 2-4/ });
    fireEvent.click(all);
    await waitFor(() => expect(screen.getByText("Picked")).toBeTruthy());
    expect(screen.getByRole("button", { name: /Unpick every animal due into 2-4/ })).toBeTruthy();
  });

  it("lets one be dropped back out again", async () => {
    // The person at the gate can see a cow this list cannot.
    draw();
    fireEvent.click(await screen.findByRole("button", { name: /Pick every animal due into 2-4/ }));
    const box = screen.getByLabelText(/Move NAserian \(A012\/25\) to 2-4/) as HTMLInputElement;
    expect(box.checked).toBe(true);
    fireEvent.click(box);
    await waitFor(() => expect(box.checked).toBe(false));
  });

  it("will not move with nothing picked", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("2-4")).toBeTruthy());
    const cards = screen.getAllByRole("button", { name: /^Move$/ });
    expect((cards[0] as HTMLButtonElement).disabled).toBe(true);
  });

  it("moves the picked set and says what happened", async () => {
    draw();
    fireEvent.click(await screen.findByRole("button", { name: /Pick every animal due into 2-4/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Move 2/ }));
    await waitFor(() =>
      expect(screen.getByText(/2 animals moved into 2-4, which now holds 7/)).toBeTruthy(),
    );
  });

  it("sends only the animals that were kept", async () => {
    draw();
    fireEvent.click(await screen.findByRole("button", { name: /Pick every animal due into 2-4/ }));
    fireEvent.click(screen.getByLabelText(/Move NAserian \(A012\/25\) to 2-4/));
    fireEvent.click(await screen.findByRole("button", { name: /Move 1/ }));
    await waitFor(() => {
      const sent = call.mock.calls.find((c) => String(c[0]).includes("move_animals"));
      expect(sent).toBeTruthy();
      const body = (sent![1] as { payload: { animals: string[] } }).payload;
      expect(body.animals).toEqual(["A013/25"]);
    });
  });

  it("the tick box is a real checkbox, circle or not", async () => {
    // Round is a look; a screen reader and the space bar still need a checkbox.
    draw();
    const box = await screen.findByLabelText(/Move APIJA \(A039\/26\)/);
    expect(box.getAttribute("type")).toBe("checkbox");
  });
});
