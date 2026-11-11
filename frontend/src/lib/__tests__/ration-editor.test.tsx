import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The Ration Editor: the ONE screen a recipe is written on.
 *
 * It took over everything Feed Design did — the feed library with its nutrient
 * badges, the live nutrition panel, kilos or % of intake with per-head doses,
 * saving as a herd's standing ration, and a concentrate where the farm has a
 * concentrate stage — and kept what the old editor pinned: SAVING IS OFFERED
 * ONLY ONCE SOMETHING CHANGED, and an UNBALANCED RECIPE IS CALLED OUT.
 *
 * Nothing here checks a nutrition figure's arithmetic (that is the server's,
 * tested in Python) or the percentage maths (ration-maths.test.ts); this pins
 * what the page shows and what it sends.
 */

const library = {
  ok: true,
  premanufacture_concentrate: false,
  any_premanufacture: true,
  feeds: [
    { item_code: "silage", item_name: "Maize Silage", category: "Forage", is_made: false, recorded: true,
      has_data: true, nutrient_source: "Book value", dry_matter_pct: 30, cp_pct: 8, carbohydrate_pct: 25,
      ndf_pct: 45, fat_pct: 3, me_mj_per_kg: 10 },
    { item_code: "germ", item_name: "Maize Germ", category: "Energy (grain / by-product)", is_made: false,
      recorded: true, has_data: true, nutrient_source: "Book value", dry_matter_pct: 88, cp_pct: 10,
      carbohydrate_pct: 50, ndf_pct: 25, fat_pct: 8, me_mj_per_kg: 12 },
    { item_code: "shoat meal", item_name: "Shoat Meal", category: "Concentrate (made)", is_made: true,
      computed: true, recorded: false, has_data: true, nutrient_source: null, dry_matter_pct: 88, cp_pct: 14,
      carbohydrate_pct: 30, ndf_pct: 30, fat_pct: 4, me_mj_per_kg: 11 },
  ],
  undescribed: [
    { item_code: "ghost", item_name: "Ghost Feed", has_data: false },
    { item_code: "molasses", item_name: "Molasses", has_data: false },
  ],
};

const herds = [
  { herd: "Finishers", heads: 300, bom: "B1", ration_item: "Finishers", ration_name: "Finishers",
    per_head_kg: 20, day_kg: 6000, lines_total: 20, balanced: true, premanufacture: false,
    lines: [
      { item_code: "silage", item_name: "Maize Silage", qty: 15, uom: "Kilogram", is_dose: false },
      { item_code: "germ", item_name: "Maize Germ", qty: 5, uom: "Kilogram", is_dose: false },
      { item_code: "dv", item_name: "Diamond V", qty: 7, uom: "Gram", is_dose: true },
    ] },
  { herd: "Finishing group 1", heads: 69, bom: "BOM-Finishing group 1-016", ration_item: "Finishing group 1",
    ration_name: "Finishing group 1", per_head_kg: 40.65, day_kg: 2804.85, lines_total: 24.5, balanced: false,
    premanufacture: false,
    lines: [
      { item_code: "silage", item_name: "Maize Silage", qty: 23, uom: "Kilogram" },
      { item_code: "hay", item_name: "Hay", qty: 1.5, uom: "Kilogram" },
    ] },
  { herd: "Growers", heads: 50, bom: "B3", ration_item: "Growers", ration_name: "Growers",
    per_head_kg: 2, day_kg: 100, lines_total: 2, balanced: true, premanufacture: false,
    lines: [{ item_code: "shoat meal", item_name: "Shoat Meal", qty: 2, uom: "Kilogram", is_dose: false }] },
  { herd: "Shoat Group 1", heads: 40, bom: "B2", ration_item: "Shoats", ration_name: "Shoats",
    per_head_kg: 1, day_kg: 40, lines_total: 1, balanced: true, premanufacture: true,
    lines: [{ item_code: "shoat meal", item_name: "Shoat Meal", qty: 1, uom: "Kilogram", is_dose: false }] },
];

const feeds = [
  { value: "silage", label: "Maize Silage", uom: "Kilogram", on_hand: 90000, is_concentrate: false },
  { value: "hay", label: "Hay", uom: "BALE", on_hand: 500, is_concentrate: false },
  { value: "shoat meal", label: "Shoat Meal", uom: "Kilogram", on_hand: 200, is_concentrate: true },
];

const shoatMeal = {
  item_code: "shoat meal", item_name: "Shoat Meal", bom_no: "BOM-SM-1", base_qty: 1000, uom: "Kilogram",
  mix_qty: 1000, in_store: 200, stores: [],
  lines: [
    { item_code: "germ", item_name: "Maize Germ", recipe_qty: 600, recipe_uom: "Kilogram", required_qty: 600 },
    { item_code: "silage", item_name: "Maize Silage", recipe_qty: 400, recipe_uom: "Kilogram", required_qty: 400 },
    { item_code: "dv", item_name: "Diamond V", recipe_qty: 7, recipe_uom: "Gram", required_qty: 7 },
  ],
};

let inUse = true;
// What the stores count in: hay in bales (1 kg = 0.07 bale), molasses in
// litres (1 kg = 0.714 L), both with a kilogram row; live names it "Kg".
const units = {
  hay: { stock_uom: "BALE", uoms: [{ uom: "BALE", factor: 1, kg: 1 / 0.07 }, { uom: "Kg", factor: 0.07, kg: 1 }] },
  molasses: { stock_uom: "Litre", uoms: [{ uom: "Litre", factor: 1, kg: 1.4 }, { uom: "Kg", factor: 0.714, kg: 1 }] },
};

const call = vi.fn(async (method?: string, _args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.includes("feed_units")) return { ok: true, units };
  if (m.includes("livestock_feeds")) return { ...library, any_premanufacture: inUse };
  if (m.includes("feed_nutrition")) return { ok: true, as_fed_kg: 0, missing: [], unpriced: [], lines: [] };
  if (m.includes("herd_rations"))
    return { ok: true, herds, feeds, premanufacture_concentrate: false, any_premanufacture: inUse };
  if (m.includes("expand_concentrate"))
    return { ok: true, expanded: ["Shoat Meal"], lines: [{ item_code: "germ", item_name: "Maize Germ", qty: 1 }] };
  if (m.includes("concentrates.concentrates")) return { ok: true, concentrates: [shoatMeal], warehouses: [] };
  if (m.includes("set_herd_ration"))
    return {
      ok: true, changed: true, bom: "BOM-Finishing group 1-017", superseded: "BOM-Finishing group 1-016",
      per_head_kg: 26.5, day_kg: 1828.5,
      differences: [
        { item_code: "silage", item_name: "Maize Silage", was: 23, now: 25, what: "raised" },
      ],
    };
  if (m.includes("set_concentrate"))
    return { ok: true, changed: true, bom: "BOM-SM-2", item: "shoat meal", base_qty: 1010 };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { RationEditor } = await import("@/pages/RationEditor");

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  window.matchMedia = ((q: string) => ({
    matches: false, media: q, onchange: null, addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  Element.prototype.scrollIntoView = () => {};
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.releasePointerCapture = () => {};
});

beforeEach(() => {
  inUse = true;
  call.mockClear();
  window.location.hash = "#/ration-editor";
  window.LIVESTOCK = { bootstrap: { premanufacture_concentrate: true } };
});
afterEach(cleanup);

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <RationEditor />
      </ToastProvider>
    </TooltipProvider>,
  );

async function pickHerd(name: string) {
  fireEvent.click(await screen.findByText(name, { selector: "span" }));
}

function sent(method: string) {
  const c = call.mock.calls.find(([m]) => String(m).includes(method));
  return (c?.[1] as { payload: { lines: unknown[]; name?: string } } | undefined)?.payload;
}

const amounts = () => screen.getAllByLabelText("Amount (kg)").map((e) => (e as HTMLInputElement).value);
const shares = () => screen.getAllByLabelText("Share (%)").map((e) => (e as HTMLInputElement).value);

const saveButton = () => screen.getByRole("button", { name: /^Save / }) as HTMLButtonElement;

describe("the Ration Editor, herd by herd", () => {
  it("lists every herd with what it eats a head, a day", async () => {
    draw();
    expect(await screen.findByText("40.65 kg × 69 head")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Ration Editor" })).toBeTruthy();
  });

  it("shows the feed library with a no-data badge for an undescribed feed", async () => {
    draw();
    await screen.findByText("Maize Germ");
    expect(screen.getByText("Ghost Feed")).toBeTruthy();
    expect(screen.getAllByText("no data").length).toBeGreaterThan(0);
  });

  it("will not save until something has actually changed", async () => {
    draw();
    await pickHerd("Finishing group 1");
    await screen.findByRole("button", { name: /Save as the Finishing group 1 ration/ });
    expect(saveButton().disabled).toBe(true);
    expect(screen.getByText("Nothing has changed yet.")).toBeTruthy();
  });

  it("enables the save once a quantity moves, and totals the herd", async () => {
    draw();
    await pickHerd("Finishing group 1");
    const amounts = await screen.findAllByLabelText("Amount (kg)");
    fireEvent.change(amounts[0], { target: { value: "25" } });
    await waitFor(() => expect(saveButton().disabled).toBe(false));
    // 25 + 1.5 across 69 head.
    expect(screen.getByText(/1,828.50 kg for 69 head/)).toBeTruthy();
    // Hay is weighed in kilos and counted in bales: both are shown.
    expect(await screen.findByText(/≈ 0\.1\d BALE/)).toBeTruthy();
  });

  it("calls out a recipe whose output and ingredients disagree, and not one that adds up", async () => {
    draw();
    await pickHerd("Finishing group 1");
    expect(await screen.findByText(/issues less feed than it consumes/)).toBeTruthy();
    await pickHerd("Finishers");
    await waitFor(() => expect(screen.queryByText(/issues less feed than it consumes/)).toBeNull());
  });

  it("reports the revision it made and what it superseded", async () => {
    draw();
    await pickHerd("Finishing group 1");
    fireEvent.change((await screen.findAllByLabelText("Amount (kg)"))[0], { target: { value: "25" } });
    fireEvent.click(saveButton());
    expect(await screen.findByText(/superseding BOM-Finishing group 1-016/)).toBeTruthy();
    expect(screen.getByText(/Maize Silage raised from 23 to 25/)).toBeTruthy();
  });

  it("loads a dose as a dose and saves it with its unit, outside the kilos", async () => {
    draw();
    await pickHerd("Finishers");
    expect(await screen.findByLabelText("Dose (g a head)")).toBeTruthy();
    expect(screen.getByText(/2\.1 kg for the herd/)).toBeTruthy();
    fireEvent.change(screen.getAllByLabelText("Amount (kg)")[0], { target: { value: "16" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(sent("set_herd_ration")).toBeTruthy());
    expect(sent("set_herd_ration")!.lines).toEqual([
      { item_code: "silage", qty: 16 },
      { item_code: "germ", qty: 5 },
      { item_code: "dv", qty: 7, dose_uom: "Gram" },
    ]);
  });

  it("typing the kg per head rescales every kilogram line and keeps the shares", async () => {
    draw();
    await pickHerd("Finishers");
    const perHead = (await screen.findByLabelText("Kg per head per day")) as HTMLInputElement;
    // No total of its own yet: the lines' sum is only a hint.
    expect(perHead.value).toBe("");
    expect(perHead.placeholder).toBe("20");
    expect(screen.getAllByLabelText("Share (%)").map((e) => (e as HTMLInputElement).value)).toEqual(["75", "25"]);
    fireEvent.change(perHead, { target: { value: "24" } });
    expect(shares()).toEqual(["75", "25"]);
    fireEvent.click(saveButton());
    await waitFor(() => expect(sent("set_herd_ration")).toBeTruthy());
    expect(sent("set_herd_ration")!.lines).toEqual([
      { item_code: "silage", qty: 18 },
      { item_code: "germ", qty: 6 },
      { item_code: "dv", qty: 7, dose_uom: "Gram" },
    ]);
  });

  it("shows kilos and % on every weighed line, both editable, and no mode switch", async () => {
    draw();
    await pickHerd("Finishers");
    const amounts = await screen.findAllByLabelText("Amount (kg)");
    expect(amounts.map((e) => (e as HTMLInputElement).readOnly)).toEqual([false, false]);
    expect(screen.getAllByLabelText("Share (%)")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "% of intake" })).toBeNull();
    // The dose has no share and no lock.
    expect(screen.getByLabelText("Dose (g a head)")).toBeTruthy();
  });

  it("with no total, typing kilos changes that line only and nothing locks", async () => {
    draw();
    await pickHerd("Finishers");
    fireEvent.change((await screen.findAllByLabelText("Amount (kg)"))[0], { target: { value: "35" } });
    expect(amounts()).toEqual(["35", "5"]);
    expect(shares()).toEqual(["87.5", "12.5"]);
    expect(screen.queryByRole("button", { name: /^(Un)?lock / })).toBeNull();
  });

  it("typing a % makes the sum the total, locks the line and rebalances the rest", async () => {
    draw();
    await pickHerd("Finishers");
    fireEvent.change((await screen.findAllByLabelText("Share (%)"))[1], { target: { value: "40" } });
    expect((screen.getByLabelText("Kg per head per day") as HTMLInputElement).value).toBe("20");
    expect(amounts()).toEqual(["12", "8"]);
    expect(screen.getByRole("button", { name: "Unlock Maize Germ" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Lock Maize Silage" })).toBeTruthy();
    fireEvent.click(saveButton());
    await waitFor(() => expect(sent("set_herd_ration")).toBeTruthy());
    expect(sent("set_herd_ration")!.lines).toEqual([
      { item_code: "silage", qty: 12 },
      { item_code: "germ", qty: 8 },
      { item_code: "dv", qty: 7, dose_uom: "Gram" },
    ]);
  });

  it("with a total, the last unlocked line cannot move and the screen says why", async () => {
    draw();
    await pickHerd("Finishers");
    fireEvent.change(await screen.findByLabelText("Kg per head per day"), { target: { value: "20" } });
    fireEvent.change(screen.getAllByLabelText("Amount (kg)")[0], { target: { value: "16" } });
    expect(amounts()).toEqual(["16", "4"]);
    fireEvent.change(screen.getAllByLabelText("Amount (kg)")[1], { target: { value: "9" } });
    expect(amounts()).toEqual(["16", "4"]);
    expect(screen.getByRole("status").textContent).toBe(
      "Locked rows already use 16 of 20 kg — unlock a row to give it more.",
    );
    // Unlocking the silage frees it to take up the germ's change.
    fireEvent.click(screen.getByRole("button", { name: "Unlock Maize Silage" }));
    fireEvent.change(screen.getAllByLabelText("Amount (kg)")[1], { target: { value: "9" } });
    expect(amounts()).toEqual(["11", "9"]);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("asks the server for the nutrition once lines are in", async () => {
    draw();
    await pickHerd("Finishers");
    await waitFor(
      () =>
        expect(
          call.mock.calls.some(
            ([m, a]) =>
              String(m).includes("feed_nutrition.feed_nutrition") &&
              String((a as { lines: string } | undefined)?.lines).includes('"qty":15'),
          ),
        ).toBe(true),
      { timeout: 2000 },
    );
  });

  it("a herd on Mix from raw is offered raw feeds only, one on Pre-manufacture its concentrate too", async () => {
    draw();
    await screen.findByText("Maize Germ");
    // Nothing chosen: some herd still eats a concentrate, so it is offered.
    expect(screen.getByLabelText("Add Shoat Meal")).toBeTruthy();
    await pickHerd("Finishers");
    await waitFor(() => expect(screen.queryByLabelText("Add Shoat Meal")).toBeNull());
    await pickHerd("Shoat Group 1");
    expect(await screen.findByLabelText("Add Shoat Meal")).toBeTruthy();
  });

  it("offers to expand a concentrate left in a raw-only herd's ration", async () => {
    draw();
    await pickHerd("Growers");
    fireEvent.click(await screen.findByRole("button", { name: /Expand into ingredients/ }));
    await waitFor(() =>
      expect(call.mock.calls.some(([m]) => String(m).includes("expand_concentrate"))).toBe(true),
    );
  });
});

describe("the Ration Editor, concentrates", () => {
  it("lists the concentrates and saves an edited one through set_concentrate", async () => {
    draw();
    fireEvent.click(await screen.findByRole("button", { name: /Shoat Meal.*3 ingredients/ }));
    const amounts = await screen.findAllByLabelText("Amount (kg)");
    expect((amounts[0] as HTMLInputElement).value).toBe("600");
    expect(screen.getByLabelText("Dose (g a head)")).toBeTruthy();
    fireEvent.change(amounts[0], { target: { value: "610" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the concentrate" }));
    await waitFor(() => expect(sent("set_concentrate")).toBeTruthy());
    expect(sent("set_concentrate")).toEqual({
      name: "Shoat Meal",
      lines: [
        { item_code: "germ", qty: 610 },
        { item_code: "silage", qty: 400 },
        { item_code: "dv", qty: 7, dose_uom: "Gram" },
      ],
    });
  });

  it("starts a new concentrate blank and needs a name to save", async () => {
    draw();
    fireEvent.click(await screen.findByRole("button", { name: /New concentrate/ }));
    expect(await screen.findByText("Name it and list what goes into one batch.")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Add Maize Germ"));
    fireEvent.change(await screen.findByLabelText("Amount (kg)"), { target: { value: "500" } });
    expect((screen.getByRole("button", { name: "Save the concentrate" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Concentrate name"), { target: { value: "Calf Starter" } });
    expect((screen.getByRole("button", { name: "Save the concentrate" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("opens straight on the concentrate a link names", async () => {
    window.location.hash = "#/ration-editor?concentrate=shoat%20meal";
    draw();
    expect(await screen.findByText("Shoat Meal · concentrate")).toBeTruthy();
    expect(((await screen.findAllByLabelText("Amount (kg)"))[0] as HTMLInputElement).value).toBe("600");
  });

  it("offers no concentrate at all where concentrate is not in use", async () => {
    inUse = false;
    window.LIVESTOCK = { bootstrap: { premanufacture_concentrate: false } };
    draw();
    await screen.findByText("Maize Germ");
    expect(screen.queryByRole("button", { name: /New concentrate/ })).toBeNull();
    expect(screen.queryByText("Shoat Meal")).toBeNull();
    expect(call.mock.calls.some(([m]) => String(m).includes("concentrates.concentrates"))).toBe(false);
  });
});

describe("the Ration Editor, a line in the store's unit", () => {
  async function addMolassesInLitres(qty: string) {
    await pickHerd("Finishers");
    fireEvent.click(await screen.findByLabelText("Add Molasses"));
    const unitPickers = await screen.findAllByLabelText("Unit");
    fireEvent.click(unitPickers[unitPickers.length - 1]);
    fireEvent.click(await screen.findByRole("option", { name: "Litre" }));
    fireEvent.change(await screen.findByLabelText("Amount (Litre)"), { target: { value: qty } });
  }

  it("offers the item's own units and shows the kilos beside the litres", async () => {
    draw();
    await addMolassesInLitres("3");
    expect(await screen.findByText(/3 Litre ≈ 4\.20 kg/)).toBeTruthy();
    // 15 + 5 kg + 3 L of molasses at 1.4 kg a litre.
    expect(screen.getByText(/24\.20 kg/)).toBeTruthy();
  });

  it("saves the line in its unit and weighs it in kilos for the nutrition", async () => {
    draw();
    await addMolassesInLitres("3");
    fireEvent.click(saveButton());
    await waitFor(() => expect(sent("set_herd_ration")).toBeTruthy());
    expect(sent("set_herd_ration")!.lines).toContainEqual({ item_code: "molasses", qty: 3, uom: "Litre" });
    await waitFor(
      () =>
        expect(
          call.mock.calls.some(
            ([m, a]) =>
              String(m).includes("feed_nutrition.feed_nutrition") &&
              String((a as { lines: string }).lines).includes('{"item_code":"molasses","qty":4.2}'),
          ),
        ).toBe(true),
      { timeout: 2000 },
    );
  });

  it("keeps the kilos when the unit changes", async () => {
    draw();
    await pickHerd("Finishing group 1");
    const unitPickers = await screen.findAllByLabelText("Unit");
    // The hay line: 1.5 kg is 0.105 bale.
    fireEvent.click(unitPickers[1]);
    fireEvent.click(await screen.findByRole("option", { name: "BALE" }));
    expect(((await screen.findByLabelText("Amount (BALE)")) as HTMLInputElement).value).toBe("0.105");
  });

  it("shares % of intake by kilos, whatever unit a line is in", async () => {
    draw();
    await addMolassesInLitres("3");
    const shares = (await screen.findAllByLabelText("Share (%)")).map((e) => (e as HTMLInputElement).value);
    // 15, 5 and 4.2 kg of 24.2.
    expect(shares).toEqual(["61.98", "20.66", "17.36"]);
    fireEvent.change(screen.getByLabelText("Kg per head per day"), { target: { value: "48.4" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(sent("set_herd_ration")).toBeTruthy());
    // Doubled: about 6 L of molasses (the shares are kept to two places).
    const molasses = (sent("set_herd_ration")!.lines as Array<{ item_code: string; qty: number; uom?: string }>)
      .find((l) => l.item_code === "molasses")!;
    expect(molasses.uom).toBe("Litre");
    expect(molasses.qty).toBeCloseTo(6, 2);
  });
});
