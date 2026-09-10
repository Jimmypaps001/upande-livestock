import { describe, expect, it } from "vitest";
import { groupStock, totalsByUom, type StoreItem } from "@/lib/stock";

/** The same hay in two stores — the shape feed_in_store returns, and the
 *  reason the page does not sum across warehouses. */
const items = [
  { item_code: "HAY", item_name: "Hay", uom: "BALE", qty: 40, warehouse: "Feed Store - KR", is_concentrate: false },
  { item_code: "HAY", item_name: "Hay", uom: "BALE", qty: 0, warehouse: "Barn - KR", is_concentrate: false },
  { item_code: "DAIRY-MEAL", item_name: "Dairy Meal", uom: "Kg", qty: 1200, warehouse: "Feed Store - KR", is_concentrate: true },
] as StoreItem[];

describe("groupStock", () => {
  it("keeps concentrate apart from the raw ingredients", () => {
    const { concentrates, ingredients, rations } = groupStock(items);
    expect(concentrates.map((i) => i.item_code)).toEqual(["DAIRY-MEAL"]);
    expect(ingredients).toHaveLength(2);
    expect(rations).toHaveLength(0);
  });

  it("treats the server's 0/1 the same as false/true", () => {
    const { concentrates } = groupStock([
      { ...items[0], is_concentrate: 1 },
      { ...items[0], is_concentrate: 0 },
    ]);
    expect(concentrates).toHaveLength(1);
  });

  it("puts a finished ration in its own group when the server names one", () => {
    const { rations, concentrates } = groupStock([
      { ...items[2], kind: "tmr", is_concentrate: false },
      { ...items[2], kind: "concentrate", is_concentrate: true },
    ]);
    expect(rations).toHaveLength(1);
    expect(concentrates).toHaveLength(1);
  });
});

describe("totalsByUom", () => {
  it("never adds bales to kilograms", () => {
    expect(totalsByUom(items)).toEqual([
      { uom: "Kg", qty: 1200 },
      { uom: "BALE", qty: 40 },
    ]);
  });
});
