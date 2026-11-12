import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BackdatedBadge, backdatedTint } from "@/components/BackdatedBadge";
import { StockPicker } from "@/components/stock/StockPicker";
import { choiceLabel, outOfStock } from "@/lib/events";

describe("backdated records are marked", () => {
  it("badges and tints only a backdated row", () => {
    render(<BackdatedBadge />);
    expect(screen.getByTestId("backdated-badge").textContent).toBe("Backdated");
    expect(backdatedTint(true)).toMatch(/amber-tint/);
    expect(backdatedTint(0)).toBe("");
  });
});

describe("out-of-stock items are offered, marked", () => {
  const out = { value: "STRAW-1", label: "Chico · out of stock", item_name: "Chico", qty: 0, in_stock: false,
    warehouse: "Fridge", locations: [] };
  const held = { value: "STRAW-2", label: "Mazira · 3 Nos in Fridge", item_name: "Mazira", qty: 3, in_stock: true,
    warehouse: "Fridge", locations: [{ warehouse: "Fridge", qty: 3 }] };

  it("labels an out-of-stock choice with what will happen", () => {
    expect(outOfStock(out)).toBe(true);
    expect(outOfStock(held)).toBe(false);
    expect(choiceLabel(out)).toBe("Chico · out of stock — saved as a draft");
    expect(choiceLabel(held)).toBe(held.label);
  });

  it("a row naming one says its issue waits as a draft", () => {
    render(
      <StockPicker
        choices={[held, out]}
        rows={[{ key: 1, item: "STRAW-1", qty: "1", store: "Fridge", batch: "" }]}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/waits as a draft on Transactions/)).toBeTruthy();
  });
});
