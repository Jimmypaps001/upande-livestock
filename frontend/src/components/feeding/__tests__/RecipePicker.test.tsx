import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { RecipePicker } from "@/components/feeding/RecipePicker";
import type { Recipe } from "@/lib/feeding";

beforeAll(() => {
  // Radix Select's open/select flow is pointer-driven; jsdom implements
  // neither hasPointerCapture nor scrollIntoView.
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false);
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {});
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {});
});

afterEach(cleanup);

function recipe(over: Partial<Recipe>): Recipe {
  return {
    bom_no: "BOM-x",
    item_code: "Incalf Heifers",
    item_name: "Incalf Heifers",
    kind: "Standing",
    is_standing: false,
    created: "2026-01-01 00:00:00.000000",
    per_head_qty: 12.3,
    uom: "Kilogram",
    times_fed: 0,
    last_fed: "",
    lines: [],
    ...over,
  };
}

/** Shaped like the real INCALF HEIFERS payload (seven recipes, `-010`
 *  carrying 1.0 where its six siblings carry 12.3) — see
 *  picker-per-head-report.md for the `bench execute` call that confirmed it
 *  against kaitet.local. Four recipes stand in for the seven here: the
 *  standing ration, an ordinary "Previous" and "Tuned" sibling, and the
 *  `-010` outlier. */
const recipes: Recipe[] = [
  recipe({ bom_no: "BOM-...-012", kind: "Standing", is_standing: true, times_fed: 12, last_fed: "2026-09-01" }),
  recipe({ bom_no: "BOM-...-007", kind: "Previous", per_head_qty: 12.3, times_fed: 30, last_fed: "2026-08-20" }),
  recipe({ bom_no: "BOM-...-004", kind: "Tuned", per_head_qty: 12.3, times_fed: 14, last_fed: "2026-07-15" }),
  recipe({ bom_no: "BOM-...-010", kind: "Previous", per_head_qty: 1.0, times_fed: 2, last_fed: "2026-05-01" }),
];

function openPicker() {
  render(<RecipePicker recipes={recipes} value="" onChange={() => {}} idPrefix="t" />);
  fireEvent.click(screen.getByRole("combobox"));
}

describe("RecipePicker", () => {
  it("shows a per-head figure for every recipe on offer — the -010 bug's guard", () => {
    openPicker();
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(recipes.length);
    expect(within(options[0]).getByText(/12\.30 Kilogram \/ head/)).toBeTruthy();
    expect(within(options[1]).getByText(/12\.30 Kilogram \/ head/)).toBeTruthy();
    expect(within(options[2]).getByText(/12\.30 Kilogram \/ head/)).toBeTruthy();
    // -010: 1.0 kg/head, not silently rounded or hidden behind its siblings' figure.
    expect(within(options[3]).getByText(/1\.00 Kilogram \/ head/)).toBeTruthy();
  });

  it("renders all three `kind` values sensibly, never blank or 'undefined'", () => {
    openPicker();
    const options = screen.getAllByRole("option");
    expect(within(options[0]).getByText("Standing ration")).toBeTruthy();
    expect(within(options[1]).getByText("Previously fed")).toBeTruthy();
    expect(within(options[2]).getByText("Tuned")).toBeTruthy();
    expect(within(options[3]).getByText("Previously fed")).toBeTruthy();
    expect(screen.queryByText(/undefined/i)).toBeNull();
  });

  it("shows times_fed and last_fed, so historical recipes are distinguishable", () => {
    openPicker();
    const options = screen.getAllByRole("option");
    expect(within(options[1]).getByText(/Fed 30×/)).toBeTruthy();
    expect(within(options[2]).getByText(/Fed 14×/)).toBeTruthy();
    expect(within(options[3]).getByText(/Fed 2×/)).toBeTruthy();
  });

  it("calls out the recipe whose per-head amount differs sharply from what the herd is usually fed", () => {
    openPicker();
    const options = screen.getAllByRole("option");
    // -010 (1.0 vs the herd's usual 12.3 — about a twelfth) is flagged...
    expect(within(options[3]).getByText(/far from what this herd is usually fed/i)).toBeTruthy();
    // ...its ordinary siblings, carrying the herd's usual amount, are not.
    expect(within(options[1]).queryByText(/far from what this herd is usually fed/i)).toBeNull();
    expect(within(options[2]).queryByText(/far from what this herd is usually fed/i)).toBeNull();
  });

  it("flags a mis-set standing ration too — not just a historical recipe", () => {
    // The real INCALF HEIFERS payload (verified via `bench execute` against
    // kaitet.local): the herd's *currently linked* standing BOM (-012) itself
    // carries per_head_qty 1.0 — the same figure as -010 — while the herd's
    // five actually-run recipes (47 Work Orders between them) all carry
    // 12.3. A comparison anchored to "whatever is standing" would miss this
    // entirely; the median-of-the-offered-set comparison must not.
    const liveShape: Recipe[] = [
      recipe({ bom_no: "BOM-...-012", kind: "Standing", is_standing: true, per_head_qty: 1.0, times_fed: 0, last_fed: "" }),
      recipe({ bom_no: "BOM-...-010", kind: "Previous", per_head_qty: 1.0, times_fed: 1, last_fed: "2026-08-27" }),
      recipe({ bom_no: "BOM-...-007", kind: "Previous", per_head_qty: 12.3, times_fed: 30, last_fed: "2026-08-25" }),
      recipe({ bom_no: "BOM-...-006", kind: "Previous", per_head_qty: 12.3, times_fed: 1, last_fed: "2026-04-20" }),
      recipe({ bom_no: "BOM-...-005", kind: "Previous", per_head_qty: 12.3, times_fed: 2, last_fed: "2026-04-19" }),
      recipe({ bom_no: "BOM-...-004", kind: "Previous", per_head_qty: 12.3, times_fed: 14, last_fed: "2026-04-18" }),
      recipe({ bom_no: "BOM-...-003", kind: "Previous", per_head_qty: 12.3, times_fed: 1, last_fed: "2026-03-25" }),
    ];
    render(<RecipePicker recipes={liveShape} value="" onChange={() => {}} idPrefix="t" />);
    fireEvent.click(screen.getByRole("combobox"));
    const options = screen.getAllByRole("option");
    expect(within(options[0]).getByText(/far from what this herd is usually fed/i)).toBeTruthy(); // standing
    expect(within(options[1]).getByText(/far from what this herd is usually fed/i)).toBeTruthy(); // -010
    expect(within(options[2]).queryByText(/far from what this herd is usually fed/i)).toBeNull(); // -007
  });
});
