import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Choosing the straw, and the store it comes out of.
 *
 * The Service form offered a "Straw used" select built with
 * `o.semen_items.map((i) => i.value)` — bare item codes, `4040030118`, with no
 * bull name and no store — and offered no way at all to say which fridge the
 * straw came from. The issue then posted from `Livestock Settings`, whatever
 * the operator had in his hand.
 *
 * On live that select was empty anyway: the lookup was pinned to one store
 * holding nothing while 361 straws sat in two others. The server half is fixed
 * in test_insemination_store; this is the half a herdsman touches.
 */

const straws = [
  {
    value: "4040030119",
    label: "Semen Usher · 30 Nos in Drug/Medicine Store - Old Office - KR",
    item_name: "Semen Usher",
    uom: "Nos",
    warehouse: "Drug/Medicine Store - Old Office - KR",
    locations: [
      { warehouse: "Drug/Medicine Store - Old Office - KR", qty: 30 },
      { warehouse: "Westwood Dairy Store - KR", qty: 4 },
    ],
  },
  {
    value: "4040030118",
    label: "Semen Chico · 12 Nos in Westwood Dairy Store - KR",
    item_name: "Semen Chico",
    uom: "Nos",
    warehouse: "Westwood Dairy Store - KR",
    locations: [{ warehouse: "Westwood Dairy Store - KR", qty: 12 }],
  },
  {
    value: "4040030129",
    label: "Semen Bolt · 7 Nos in Drug/Medicine Store - Old Office - KR",
    item_name: "Semen Bolt",
    uom: "Nos",
    warehouse: "Drug/Medicine Store - Old Office - KR",
    locations: [{ warehouse: "Drug/Medicine Store - Old Office - KR", qty: 7 }],
  },
];

const breeding: Record<string, unknown> = {
  ok: true,
  animals: [
    { name: "A039/26", label: "APIJA (A039/26)", herd: "Lactating group 1", herd_label: "Lactating group 1", repro: "Open" },
  ],
  diagnosis_animals: [],
  heat_animals: [],
  service_types: ["A.I.", "Natural"],
  diagnosis_results: ["Confirmed", "Not Pregnant"],
  sires: ["BULL-1"],
  semen_items: straws,
  default_semen_item: null,
  service_wait_days: 60,
  employee: "HR-EMP-001" as string | null,
};

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  if ((method || "").includes("create_service_event")) {
    sent.push(args ?? {});
    return { ok: true, name: "SERVICE-2026-0001" };
  }
  if ((method || "").includes("event_batches")) return { ok: true, lines: [] };
  return breeding;
});
const sent: Record<string, unknown>[] = [];

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Service } = await import("@/pages/Breeding");

async function choose(label: string, option: RegExp | string) {
  fireEvent.click(screen.getByLabelText(label));
  const row = await screen.findByRole("option", { name: option });
  fireEvent.click(row);
}

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <Service />
      </ToastProvider>
    </TooltipProvider>,
  );

async function pickTheCow() {
  draw();
  await waitFor(() => expect(screen.getByText("APIJA (A039/26)")).toBeTruthy());
  fireEvent.click(screen.getByText("APIJA (A039/26)"));
}

describe("the insemination pickers", () => {
  beforeEach(() => {
    call.mockClear();
    sent.length = 0;
    delete breeding.items_by_event;
  });

  it("names the bull and the store on the straw, not the item code", async () => {
    await pickTheCow();
    fireEvent.click(screen.getByLabelText("Straw used"));
    expect(
      await screen.findByRole("option", { name: /Semen Chico · 12 Nos in Westwood Dairy Store/ }),
    ).toBeTruthy();
  });

  it("offers a store only once a straw is chosen", async () => {
    await pickTheCow();
    // Nothing to choose between before there is a straw to have stores.
    expect(screen.queryByLabelText("From store")).toBeNull();
    await choose("Straw used", /Semen Usher/);
    await waitFor(() => expect(screen.getByLabelText("From store")).toBeTruthy());
  });

  it("starts on the store holding the most of that straw", async () => {
    await pickTheCow();
    await choose("Straw used", /Semen Usher/);
    await waitFor(() =>
      expect(
        screen.getByLabelText("From store").textContent,
      ).toContain("Drug/Medicine Store - Old Office - KR"),
    );
  });

  it("moves off a store that does not hold the newly chosen straw", async () => {
    // Chico is only in Westwood; Bolt is only in the Old Office. Leaving
    // Westwood on the form would name a fridge that has no Bolt in it, and
    // the issue would ask a shelf for stock it has never held.
    await pickTheCow();
    await choose("Straw used", /Semen Chico/);
    await waitFor(() =>
      expect(screen.getByLabelText("From store").textContent).toContain("Westwood Dairy Store"),
    );
    await choose("Straw used", /Semen Bolt/);
    await waitFor(() =>
      expect(screen.getByLabelText("From store").textContent).toContain(
        "Drug/Medicine Store - Old Office - KR",
      ),
    );
  });

  it("keeps a store the operator chose when it holds the new straw too", async () => {
    // He is standing at that fridge. Usher is in both stores, so a deliberate
    // choice of Westwood survives a change of straw — the auto-pick is a
    // starting point, not a correction.
    await pickTheCow();
    await choose("Straw used", /Semen Usher/);
    await choose("From store", /Westwood Dairy Store/);
    await choose("Straw used", /Semen Chico/);
    await waitFor(() =>
      expect(screen.getByLabelText("From store").textContent).toContain("Westwood Dairy Store"),
    );
  });

  it("asks how many straws, starting at one", async () => {
    // A double insemination within one day is real practice — guards.py says
    // so — and the form had no way to say "two". Every service deducted
    // exactly one straw whatever was actually used.
    await pickTheCow();
    const field = screen.getByLabelText("Straws used") as HTMLInputElement;
    expect(field.value).toBe("1");
  });

  it("deducts the count the operator typed, not one", async () => {
    await pickTheCow();
    await choose("How", "A.I.");
    await choose("Straw used", /Semen Usher/);
    fireEvent.change(screen.getByLabelText("Straws used"), { target: { value: "2" } });
    const button = screen.getByRole("button", { name: /Record the service/ });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(sent.length).toBe(1));
    expect((sent[0].payload as Record<string, unknown>).semen_qty).toBe(2);
  });

  it("sends the straw and the chosen store to the server", async () => {
    await pickTheCow();
    await choose("How", "A.I.");
    await choose("Straw used", /Semen Usher/);
    await choose("From store", /Westwood Dairy Store/);
    const button = screen.getByRole("button", { name: /Record the service/ });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(sent.length).toBe(1));
    const payload = sent[0].payload as Record<string, unknown>;
    expect(payload.semen_item).toBe("4040030119");
    expect(payload.semen_warehouse).toBe("Westwood Dairy Store - KR");
  });

  describe("when the farm has mapped Service to an item group", () => {
    beforeEach(() => {
      breeding.items_by_event = { Service: straws };
    });

    it("shows the shared Items table and none of the bespoke straw fields", async () => {
      await pickTheCow();
      expect(await screen.findByLabelText("Item")).toBeTruthy();
      expect(screen.queryByLabelText("Straw used")).toBeNull();
      expect(screen.queryByLabelText("Straws used")).toBeNull();
    });

    it("posts the straw as an items row and writes no legacy field", async () => {
      await pickTheCow();
      await choose("How", "A.I.");
      fireEvent.click(await screen.findByLabelText("Item"));
      fireEvent.click(await screen.findByRole("option", { name: /Semen Chico/ }));
      const button = screen.getByRole("button", { name: /Record the service/ });
      await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
      fireEvent.click(button);
      await waitFor(() => expect(sent.length).toBe(1));
      const payload = sent[0].payload as Record<string, unknown>;
      const items = payload.items as Array<Record<string, unknown>>;
      expect(items).toHaveLength(1);
      expect(items[0]).toMatchObject({ item_code: "4040030118", qty: 1, source_warehouse: "Westwood Dairy Store - KR" });
      // Absent or undefined, never "" (an empty string reads as a batch named "").
      expect(items[0].batch_no).toBeUndefined();
      expect(items[0].batch_no).not.toBe("");
      expect(payload.semen_item).toBeUndefined();
      expect(payload.semen_warehouse).toBeUndefined();
    });
  });

  it("keeps the straw picker and shows no Items table while Service is unmapped", async () => {
    await pickTheCow();
    expect(screen.getByLabelText("Straw used")).toBeTruthy();
    expect(screen.queryByLabelText("Item")).toBeNull();
    expect(screen.queryByText(/Nothing mapped to this event is in stock right now/)).toBeNull();
  });
});
