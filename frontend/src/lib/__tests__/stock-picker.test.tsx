import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { StockPicker, blankRow, type ItemRow } from "@/components/stock/StockPicker";
import { planKey } from "@/lib/use-batch-plans";

/**
 * What a record used, out of the stores that hold it: one grid of rows that
 * every page whose event posts stock imports.
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
      <StockPicker choices={choices} rows={rows} onChange={onChange} />
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
    const onChange = draw([{ key: 1, item: "DRUG-A", qty: "2", store: "General Store Karen - KR", batch: "" }]);
    fireEvent.click(screen.getByLabelText("From store"));
    fireEvent.click(await screen.findByRole("option", { name: /Westwood Dairy Store - KR/ }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect((onChange.mock.calls.at(-1)![0] as ItemRow[])[0].store).toBe("Westwood Dairy Store - KR");
  });

  it("shows nothing at all when the event consumes nothing", () => {
    render(
      <TooltipProvider>
        <StockPicker choices={[]} rows={[blankRow()]} onChange={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.queryByLabelText("Item")).toBeNull();
  });
});

describe("quantity defaults and an empty mapping", () => {
  it("starts an added row blank when the caller says doses are per animal", () => {
    const onChange = vi.fn();
    render(
      <TooltipProvider>
        <StockPicker choices={choices} rows={[blankRow("")]} onChange={onChange} defaultQty="" />
      </TooltipProvider>,
    );
    fireEvent.click(screen.getByText("Add item"));
    const rows = onChange.mock.calls.at(-1)![0] as ItemRow[];
    expect(rows[1].qty).toBe("");
  });

  it("starts an added row at 1 by default", () => {
    const onChange = draw([blankRow()]);
    fireEvent.click(screen.getByText("Add item"));
    expect((onChange.mock.calls.at(-1)![0] as ItemRow[])[1].qty).toBe("1");
  });

  it("says nothing mapped to the event is in stock, and does not send a configured farm to Settings", () => {
    render(
      <TooltipProvider>
        <StockPicker choices={[]} rows={[blankRow()]} onChange={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.getByText(/Nothing mapped to this event is in stock right now/)).toBeTruthy();
    expect(screen.queryByText(/not set to post stock/)).toBeNull();
    expect(screen.queryByText(/Settings/)).toBeNull();
  });

  it("with mapped={false}, says nothing is mapped and where to map it", () => {
    render(
      <TooltipProvider>
        <StockPicker choices={[]} mapped={false} rows={[blankRow()]} onChange={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.getByText(/not set to post stock/)).toBeTruthy();
    expect(screen.getByText(/Settings → Stock/)).toBeTruthy();
    expect(screen.queryByText(/in stock right now/)).toBeNull();
  });
});

const KEY = planKey("DRUG-A", "General Store Karen - KR");

describe("naming a batch", () => {
  const plans = {
    [planKey("DRUG-A", "General Store Karen - KR")]: {
      item_code: "DRUG-A", warehouse: "General Store Karen - KR",
      required_qty: 2, tracked: true,
      picks: [{ batch_no: "B-1", qty: 2 }], short: 0, blocked_by: [],
      available: [{ batch_no: "B-1", qty: 9, expiry_date: null }],
    },
  };

  it("offers the batches the store actually holds", async () => {
    render(
      <TooltipProvider>
        <StockPicker
          choices={choices}
          rows={[{ key: 1, item: "DRUG-A", qty: "2", store: "General Store Karen - KR", batch: "" }]}
          plans={plans}
          onChange={vi.fn()}
        />
      </TooltipProvider>,
    );
    fireEvent.click(screen.getByLabelText("Batch"));
    expect(await screen.findByRole("option", { name: /B-1/ })).toBeTruthy();
  });

  it("says so rather than offering a picker when the item is not batched", () => {
    render(
      <TooltipProvider>
        <StockPicker
          choices={choices}
          rows={[{ key: 1, item: "DRUG-A", qty: "2", store: "General Store Karen - KR", batch: "" }]}
          plans={{ [KEY]: { ...plans[KEY], tracked: false, picks: [], available: [] } }}
          onChange={vi.fn()}
        />
      </TooltipProvider>,
    );
    expect(screen.queryByLabelText("Batch")).toBeNull();
    expect(screen.getByText("not batched")).toBeTruthy();
  });

  it("says nothing about batches while no plan has arrived", () => {
    draw([{ key: 1, item: "DRUG-A", qty: "2", store: "General Store Karen - KR", batch: "" }]);
    expect(screen.queryByLabelText("Batch")).toBeNull();
    expect(screen.queryByText("not batched")).toBeNull();
  });

  it("starts a blank row with no batch", () => {
    expect(blankRow().batch).toBe("");
  });
});

describe("a plan for another store is never shown", () => {
  it("ignores a plan whose warehouse is not the row's store, however it was keyed", () => {
    const wrong = {
      item_code: "DRUG-A", warehouse: "Westwood Dairy Store - KR", required_qty: 1, tracked: true,
      picks: [], short: 0, blocked_by: [],
      available: [{ batch_no: "WRONG-STORE", qty: 3, expiry_date: null }],
    };
    render(
      <TooltipProvider>
        <StockPicker
          choices={choices}
          rows={[{ key: 1, item: "DRUG-A", qty: "1", store: "General Store Karen - KR", batch: "" }]}
          plans={{ [KEY]: wrong }}
          onChange={vi.fn()}
        />
      </TooltipProvider>,
    );
    expect(screen.queryByLabelText("Batch")).toBeNull();
    expect(screen.queryByText("not batched")).toBeNull();
  });
});

describe("the grid", () => {
  it("has one header for every row, numbered", () => {
    draw([{ ...blankRow(), item: "DRUG-A", store: "General Store Karen - KR" }, blankRow()]);
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(
      ["No.", "Item", "Qty", "UOM", "From store", "Batch", "Remove"],
    );
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByText("CAN")).toBeTruthy();
  });

  it("drops a row with its ×", () => {
    const a = { ...blankRow(), item: "DRUG-A" };
    const b = blankRow();
    const onChange = draw([a, b]);
    fireEvent.click(screen.getByLabelText("Remove row 1"));
    expect(onChange).toHaveBeenLastCalledWith([b]);
  });

  it("clears the last row instead of leaving nothing to type into", () => {
    const onChange = draw([{ ...blankRow(), item: "DRUG-A", qty: "3" }]);
    fireEvent.click(screen.getByLabelText("Remove row 1"));
    const rows = onChange.mock.calls.at(-1)![0] as ItemRow[];
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ item: "", qty: "1", store: "", batch: "" });
  });
});
