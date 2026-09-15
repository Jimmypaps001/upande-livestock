import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Opening a case, from the screen's side.
 *
 * What is protected here is that the form is USABLE with four hundred animals
 * on the farm. It was not: the picker was an unbounded list, so the flow cards,
 * the reason box and the button that actually opens the case were pushed below
 * the fold — the screen read as a list you could not select from and a form
 * with no submit.
 */

const animals = Array.from({ length: 40 }, (_, i) => ({
  name: `A0${String(i).padStart(2, "0")}/22`,
  burn_name: `COW-${i}`,
  sex: "Female" as const,
  current_herd: "Lactating group 1",
  breed: "Ayrshire",
  date_of_birth: "2022-03-04",
  image: null,
}));

const payloads: Record<string, unknown> = {
  cull_board: {
    ok: true,
    animals,
    cases: [],
    flagged: [],
    recent: [],
    open_claims: [],
    counts: { awaiting_vet: 0, awaiting_approval: 0, ready_to_post: 0, flagged: 0 },
  },
  cull_evidence: {
    ok: true,
    animal: "A000/22",
    name: "COW-0",
    herd: "Lactating group 1",
    status: "Active",
    measures: [],
    below: 0,
    measured: 0,
    was_productive: false,
    case: "There are no figures on her yet to compare.",
    book_value: 0,
    is_capitalised: false,
    asset: null,
    policy: null,
  },
  cull_candidates: {
    ok: true,
    candidates: [],
    considered: 40,
    flagged_count: 0,
    herd: {},
    per_animal_milk: false,
  },
};

const call = vi.fn(async (method?: string) => {
  const key = Object.keys(payloads)
    .filter((k) => (method || "").includes(k))
    .sort((a, b) => b.length - a.length)[0];
  return key ? payloads[key] : { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Culling } = await import("@/pages/Culling");

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <Culling />
      </ToastProvider>
    </TooltipProvider>,
  );

async function openTheRaiseTab() {
  draw();
  // Radix tabs activate on FOCUS, not on a synthetic click — activationMode is
  // automatic, and a jsdom click never moves focus.
  const tab = await waitFor(() => screen.getByRole("tab", { name: /Open a case/ }));
  fireEvent.focus(tab);
  await waitFor(() => expect(screen.getByText("Which animal")).toBeTruthy());
}

describe("opening a cull case", () => {
  it("offers the four ways an animal leaves", async () => {
    await openTheRaiseTab();
    for (const flow of ["Sell her", "Dispose of her", "Record a death", "Give her away"]) {
      expect(screen.getByText(flow)).toBeTruthy();
    }
  });

  it("will not open a case until an animal is picked, and says so", async () => {
    await openTheRaiseTab();
    const button = screen.getByRole("button", { name: /Open the case/ }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText(/Pick an animal first/)).toBeTruthy();
  });

  it("picking an animal from the list arms the button and names her", async () => {
    await openTheRaiseTab();
    fireEvent.click(screen.getByText("COW-7"));
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: /Open the case/ }) as HTMLButtonElement).disabled,
      ).toBe(false),
    );
    // Named where the decision is made, not only as a highlighted row that is
    // scrolled out of sight by the time you reach the flow.
    expect(screen.getAllByText("COW-7").length).toBeGreaterThan(1);
  });

  it("keeps the long list inside its own scroller", async () => {
    await openTheRaiseTab();
    const list = screen.getByText("Which animal").parentElement as HTMLElement;
    expect(list.className).toContain("overflow-hidden");
    expect(list.className).toContain("max-h-");
  });
});
