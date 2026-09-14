import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The Culling page, actually rendered.
 *
 * A page that compiles is not a page that draws: the two things this catches
 * are a card that throws on an empty board and a chain that offers a button
 * the case is not at yet. Both are one-line mistakes that a type check cannot
 * see and that nobody finds until a farm opens the page.
 */

const board = {
  ok: true,
  animals: [
    {
      name: "A039/26",
      burn_name: "APIJA",
      sex: "Female" as const,
      current_herd: "Lactating group 1",
      breed: "Ayrshire",
      date_of_birth: "2022-04-11",
      image: null,
    },
  ],
  cases: [
    {
      name: "ANI-DISP-2026-00099",
      animal: "A057/22",
      animal_name: "NDAMA",
      herd: "Lactating group 1",
      disposal_date: "2026-09-12",
      disposal_type: "Sold",
      flow: "Sale" as const,
      status: "Awaiting Vet" as const,
      waiting_on: "the vet",
      evidence: "She is below the herd on three of five measures.",
      was_productive: false,
      death_cause: null,
      vet_verdict: null,
      vet_on: null,
      sale_price: 0,
      buyer_name: null,
      gifted_to: null,
    },
  ],
  flagged: [
    { name: "A101/23", burn_name: "SITA", herd: "Lactating group 2", reason: "Three mastitis cases", marked_on: "2026-09-01", marked_by: "x@y.z" },
  ],
  recent: [],
  open_claims: [],
  counts: { awaiting_vet: 1, awaiting_approval: 0, ready_to_post: 0, flagged: 1 },
};

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call: vi.fn(async () => board) };
});

const { Culling } = await import("@/pages/Culling");

function draw() {
  return render(
    <TooltipProvider>
      <ToastProvider>
      <Culling />
    </ToastProvider>
    </TooltipProvider>,
  );
}

describe("the culling page", () => {
  beforeEach(() => vi.clearAllMocks());

  it("draws the queue with the case on it", async () => {
    draw();
    // Twice: once as the row in the queue, once as the heading of the panel it
    // opened. The queue and the case being read are the same page.
    await waitFor(() => expect(screen.getAllByText("NDAMA").length).toBe(2));
    expect(screen.getAllByText(/With the vet/).length).toBeGreaterThan(0);
  });

  it("shows the argument that was made on the day", async () => {
    draw();
    await waitFor(() =>
      expect(screen.getByText("She is below the herd on three of five measures.")).toBeTruthy(),
    );
  });

  it("offers only the verdict, not the approval, on a case still with the vet", async () => {
    // Offering a button the server will refuse is worse than offering none.
    draw();
    await waitFor(() => expect(screen.getByText("Fit for sale")).toBeTruthy());
    expect(screen.queryByText("Approve")).toBeNull();
    expect(screen.queryByText("Post it")).toBeNull();
  });

  it("does not offer 'Recommends disposal' on a sale", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("Fit for sale")).toBeTruthy());
    expect(screen.queryByText("Recommends disposal")).toBeNull();
  });

  it("lists an animal marked for review that has no case yet", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("SITA")).toBeTruthy());
  });

  it("counts what is waiting on whom", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("With the vet")).toBeTruthy());
    expect(screen.getByText("Marked for review")).toBeTruthy();
  });
});
