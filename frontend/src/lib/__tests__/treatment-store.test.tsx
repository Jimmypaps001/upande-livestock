import { describe, expect, it } from "vitest";
import { drugRowsForIssue } from "@/lib/drug-lines";

/**
 * A treatment line carries the store its drug is actually in.
 *
 * `drugRowsForIssue` already attaches the per-item warehouse for EVENT drug
 * rows. The Treatment screen never used it, so every treatment went out of
 * `Livestock Settings.drug_warehouse` — on live, a store with zero stocked
 * bins, while the drugs sat in three others.
 */

const choices = [
  { value: "DRUG-A", label: "Alamyan Spray · 16 CAN in Westwood Dairy Store - KR",
    warehouse: "Westwood Dairy Store - KR",
    locations: [{ warehouse: "Westwood Dairy Store - KR", qty: 16 }] },
  { value: "DRUG-B", label: "Absorbale Sutures · 10 Piece(s) in General Store Karen - KR",
    warehouse: "General Store Karen - KR",
    locations: [{ warehouse: "General Store Karen - KR", qty: 10 }] },
];

describe("a treatment line", () => {
  it("takes each drug from the store that holds it", () => {
    const rows = drugRowsForIssue(
      [{ item_code: "DRUG-A", qty: 2 }, { item_code: "DRUG-B", qty: 1 }],
      choices,
    );
    expect(rows[0].source_warehouse).toBe("Westwood Dairy Store - KR");
    expect(rows[1].source_warehouse).toBe("General Store Karen - KR");
  });

  it("carries a batch when one was chosen", () => {
    const rows = drugRowsForIssue(
      [{ item_code: "DRUG-A", qty: 2, batch_no: "DAIR-2026-00277" }],
      choices,
    );
    expect(rows[0].batch_no).toBe("DAIR-2026-00277");
  });

  it("leaves the batch out when none was chosen", () => {
    const rows = drugRowsForIssue([{ item_code: "DRUG-A", qty: 2 }], choices);
    expect(rows[0].batch_no).toBeUndefined();
  });
});
