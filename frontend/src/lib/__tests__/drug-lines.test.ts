/**
 * A drug line is issued from the store that actually holds the drug.
 *
 * The husbandry form used to send one `source_warehouse` for the whole event —
 * `Livestock Settings.drug_warehouse` — so every line was drawn off one shelf
 * whatever the picker had said about where the stock was. On the live site
 * that shelf has no stock at all: the drugs are spread across the Old Office
 * drug store, the Westwood store, General Store Karen, the Delivery Truck and
 * the Clinic. An issue against the configured store could not have found any
 * of them.
 *
 * Each choice now carries the warehouse its stock is in, so each line goes
 * back with its own.
 */

import { describe, expect, it } from "vitest";

import { drugRowsForIssue } from "@/lib/drug-lines";

const OXYTET = {
  value: "D1",
  label: "Oxytet · 40 Litre in Clinic Store - KR",
  item_name: "Oxytet",
  qty: 40,
  uom: "Litre",
  warehouse: "Clinic Store - KR",
};
const BETAMOX = {
  value: "D2",
  label: "Betamox · 3 Vial in Delivery Truck - KR",
  item_name: "Betamox",
  qty: 3,
  uom: "Vial",
  warehouse: "Delivery Truck - KR",
};

describe("drugRowsForIssue", () => {
  it("draws each line from the store that holds that drug", () => {
    const rows = drugRowsForIssue(
      [
        { item_code: "D1", qty: "2" },
        { item_code: "D2", qty: "1" },
      ],
      [OXYTET, BETAMOX],
    );
    expect(rows).toEqual([
      { item_code: "D1", qty: 2, source_warehouse: "Clinic Store - KR" },
      { item_code: "D2", qty: 1, source_warehouse: "Delivery Truck - KR" },
    ]);
  });

  it("drops a line with no drug chosen", () => {
    expect(drugRowsForIssue([{ item_code: "", qty: "2" }], [OXYTET])).toEqual([]);
  });

  it("drops a line with no quantity", () => {
    expect(drugRowsForIssue([{ item_code: "D1", qty: "0" }], [OXYTET])).toEqual([]);
    expect(drugRowsForIssue([{ item_code: "D1", qty: "" }], [OXYTET])).toEqual([]);
  });

  it("leaves the warehouse off a drug it cannot place", () => {
    // The server then falls back to the configured store, which is what it
    // did for every line before this existed.
    expect(drugRowsForIssue([{ item_code: "D9", qty: "1" }], [OXYTET])).toEqual([
      { item_code: "D9", qty: 1, source_warehouse: undefined },
    ]);
  });

  it("keeps two lines of the same drug apart", () => {
    // Two doses of one drug at different quantities is a real thing a round
    // does; they must not be collapsed here, because the server sums them.
    const rows = drugRowsForIssue(
      [
        { item_code: "D1", qty: "2" },
        { item_code: "D1", qty: "3" },
      ],
      [OXYTET],
    );
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.source_warehouse === "Clinic Store - KR")).toBe(true);
  });
});
