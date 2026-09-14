import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Changing what a herd is fed.
 *
 * Two things worth pinning. SAVING IS DISABLED UNTIL SOMETHING CHANGES —
 * a farm correcting the same way every morning must not accumulate a BOM a
 * day, and the cheapest place to stop that is before the round trip. And an
 * UNBALANCED RECIPE IS CALLED OUT: six of the live site's rations state an
 * output their own ingredients do not add up to, which means they issue less
 * feed than they consume.
 */

const herds = [
  {
    herd: "Lactating group 1",
    heads: 69,
    bom: "BOM-Lactating Group 1-016",
    ration_item: "Lactating Group 1",
    ration_name: "Lactating Group 1",
    per_head_kg: 40.65,
    day_kg: 2804.85,
    lines: [
      { item_code: "4040010082", item_name: "Silage - Farm Produced", qty: 23, uom: "Kilogram" },
      { item_code: "4040010034", item_name: "Hay", qty: 1.5, uom: "Kilogram" },
    ],
    lines_total: 24.5,
    balanced: false,
  },
  {
    herd: "0-2",
    heads: 29,
    bom: "BOM-TMR Calves Meal-013",
    ration_item: "TMR Calves Meal",
    ration_name: "TMR Calves Meal",
    per_head_kg: 3,
    day_kg: 87,
    lines: [{ item_code: "Calves Meal", item_name: "Calves Meal", qty: 3, uom: "Kilogram" }],
    lines_total: 3,
    balanced: true,
  },
];

const feeds = [
  { value: "4040010082", label: "Silage - Farm Produced", uom: "Kilogram", on_hand: 90179 },
  { value: "4040010034", label: "Hay", uom: "BALE", on_hand: 500 },
  { value: "Calves Meal", label: "Calves Meal", uom: "Kilogram", on_hand: 257 },
];

const call = vi.fn(async (method?: string) =>
  (method || "").includes("set_herd_ration")
    ? {
        ok: true, bom: "BOM-Lactating Group 1-017", changed: true,
        superseded: "BOM-Lactating Group 1-016", per_head_kg: 26.5,
        item: "Lactating Group 1", herd: "Lactating group 1", heads: 69, day_kg: 1828.5,
        differences: [
          { item_code: "4040010082", item_name: "Silage - Farm Produced", was: 23, now: 25, what: "raised" },
        ],
      }
    : { ok: true, herds, feeds },
);

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { RationEditor } = await import("@/pages/RationEditor");

const draw = () =>
  render(
    <TooltipProvider>
      <RationEditor />
    </TooltipProvider>,
  );

describe("the ration editor", () => {
  beforeEach(() => call.mockClear());

  it("shows what each herd eats a head and a day", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("40.65 kg × 69 head")).toBeTruthy());
  });

  it("will not save until something has actually changed", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("Lactating group 1")).toBeTruthy());
    fireEvent.click(screen.getByText("Lactating group 1"));
    const save = await screen.findByRole("button", { name: /Save as a new revision/ });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Nothing has changed yet.")).toBeTruthy();
  });

  it("enables the save once a quantity moves, and totals the herd", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("Lactating group 1")).toBeTruthy());
    fireEvent.click(screen.getByText("Lactating group 1"));
    // One "Amount" per ingredient — the silage line is the first.
    const amounts = await screen.findAllByLabelText("Amount");
    fireEvent.change(amounts[0], { target: { value: "25" } });
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: /Save as a new revision/ }) as HTMLButtonElement)
          .disabled,
      ).toBe(false),
    );
    // 25 + 1.5 across 69 head.
    expect(screen.getByText(/1,828.50 kg for 69 head/)).toBeTruthy();
  });

  it("calls out a recipe whose output and ingredients disagree", async () => {
    // It issues less feed than it consumes — the live site's actual defect.
    draw();
    await waitFor(() => expect(screen.getByText("Lactating group 1")).toBeTruthy());
    fireEvent.click(screen.getByText("Lactating group 1"));
    await waitFor(() =>
      expect(screen.getByText(/issues less feed than it consumes/)).toBeTruthy(),
    );
  });

  it("says nothing is wrong with a recipe that adds up", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("0-2")).toBeTruthy());
    fireEvent.click(screen.getByText("0-2"));
    await screen.findAllByLabelText("Amount");
    expect(screen.queryByText(/issues less feed than it consumes/)).toBeNull();
  });

  it("reports the revision it made and what it superseded", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("Lactating group 1")).toBeTruthy());
    fireEvent.click(screen.getByText("Lactating group 1"));
    fireEvent.change((await screen.findAllByLabelText("Amount"))[0], {
      target: { value: "25" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save as a new revision/ }));
    await waitFor(() =>
      expect(screen.getByText(/superseding BOM-Lactating Group 1-016/)).toBeTruthy(),
    );
    expect(screen.getByText(/Silage - Farm Produced raised from 23 to 25/)).toBeTruthy();
  });
});
