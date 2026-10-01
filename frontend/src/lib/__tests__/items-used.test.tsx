import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ItemsUsed, blankRow, type ItemRow } from "@/components/events/ItemsUsed";

/**
 * What this event used, out of the stores that hold it.
 *
 * Husbandry and Treatment each grew their own drug rows, so a third event
 * wanting a list had nowhere to get one. This is that list, once.
 */

const choices = [
  { value: "DRUG-A", label: "Alamyan Spray · 16 CAN in General Store Karen - KR",
    item_name: "Alamyan Spray", qty: 16, uom: "CAN",
    warehouse: "General Store Karen - KR",
    locations: [
      { warehouse: "General Store Karen - KR", qty: 16 },
      { warehouse: "Westwood Dairy Store - KR", qty: 4 },
    ] },
];

function draw(rows: ItemRow[], onChange = vi.fn()) {
  render(
    <TooltipProvider>
      <ItemsUsed choices={choices} rows={rows} onChange={onChange} />
    </TooltipProvider>,
  );
  return onChange;
}

describe("what this event used", () => {
  it("offers the items the server said it may consume", async () => {
    draw([blankRow()]);
    fireEvent.click(screen.getByLabelText("Item"));
    expect(
      await screen.findByRole("option", { name: /Alamyan Spray · 16 CAN in General Store Karen/ }),
    ).toBeTruthy();
  });

  it("starts on the store holding the most once an item is chosen", async () => {
    const onChange = draw([blankRow()]);
    fireEvent.click(screen.getByLabelText("Item"));
    fireEvent.click(await screen.findByRole("option", { name: /Alamyan Spray/ }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const rows = onChange.mock.calls.at(-1)![0] as ItemRow[];
    expect(rows[0].item).toBe("DRUG-A");
    expect(rows[0].store).toBe("General Store Karen - KR");
  });

  it("lets the store be changed to any other that holds it", async () => {
    const onChange = draw([{ key: 1, item: "DRUG-A", qty: "2", store: "General Store Karen - KR" }]);
    fireEvent.click(screen.getByLabelText("From store"));
    fireEvent.click(await screen.findByRole("option", { name: /Westwood Dairy Store - KR/ }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect((onChange.mock.calls.at(-1)![0] as ItemRow[])[0].store).toBe("Westwood Dairy Store - KR");
  });

  it("shows nothing at all when the event consumes nothing", () => {
    render(
      <TooltipProvider>
        <ItemsUsed choices={[]} rows={[blankRow()]} onChange={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.queryByLabelText("Item")).toBeNull();
  });
});
