import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Feeding the way Mutara feeds, on the screens: percentage mode and doses in
 * Feed Design, a herd's own concentrate setting overriding the farm's, typed
 * group totals in Manufacture all, and swapping a forage on dry matter.
 *
 * The maths behind each is tested on its own (ration-maths.test.ts and the
 * Python tests); this pins what the page sends.
 */

const library = {
  ok: true,
  premanufacture_concentrate: true,
  any_premanufacture: true,
  feeds: [
    { item_code: "silage", item_name: "Maize Silage", category: "Forage", is_made: false, recorded: true,
      has_data: true, nutrient_source: "Book value", dry_matter_pct: 30, cp_pct: 8, carbohydrate_pct: 25,
      ndf_pct: 45, fat_pct: 3, me_mj_per_kg: 10, substitute_group: "Wet forage" },
    { item_code: "germ", item_name: "Maize Germ", category: "Energy (grain / by-product)", is_made: false,
      recorded: true, has_data: true, nutrient_source: "Book value", dry_matter_pct: 88, cp_pct: 10,
      carbohydrate_pct: 50, ndf_pct: 25, fat_pct: 8, me_mj_per_kg: 12 },
    { item_code: "shoat meal", item_name: "Shoat Meal", category: "Concentrate (made)", is_made: true,
      computed: true, recorded: false, has_data: true, nutrient_source: null, dry_matter_pct: 88, cp_pct: 14,
      carbohydrate_pct: 30, ndf_pct: 30, fat_pct: 4, me_mj_per_kg: 11 },
  ],
  undescribed: [],
};

const herds = [
  { herd: "Finishers", heads: 300, bom: "B1", ration_item: "Finishers", ration_name: "Finishers",
    per_head_kg: 20, day_kg: 6000, lines_total: 20, balanced: true, premanufacture: false,
    lines: [
      { item_code: "silage", item_name: "Maize Silage", qty: 15, uom: "Kilogram", is_dose: false },
      { item_code: "germ", item_name: "Maize Germ", qty: 5, uom: "Kilogram", is_dose: false },
      { item_code: "dv", item_name: "Diamond V", qty: 7, uom: "Gram", is_dose: true },
    ] },
  { herd: "Shoat Group 1", heads: 40, bom: "B2", ration_item: "Shoats", ration_name: "Shoats",
    per_head_kg: 1, day_kg: 40, lines_total: 1, balanced: true, premanufacture: true,
    lines: [{ item_code: "shoat meal", item_name: "Shoat Meal", qty: 1, uom: "Kilogram", is_dose: false }] },
];

const preview = {
  ok: true, preview: true, date: "2026-11-11", premanufacture_concentrate: false, feed_by_head_count: false,
  concentrates: [],
  herds: [
    { herd: "Finishers", heads: 300, portion: 1, qty: 6000, suggested_qty: 6000, premanufacture: false },
    { herd: "Shoat Group 1", heads: 40, portion: 1, qty: 40, suggested_qty: 40, premanufacture: true },
  ],
  skipped: [],
};

const call = vi.fn(async (method?: string, _args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.includes("livestock_feeds")) return library;
  if (m.includes("feed_nutrition")) return { ok: true, as_fed_kg: 0, missing: [], unpriced: [], lines: [] };
  if (m.includes("herd_rations"))
    return { ok: true, herds, feeds: [], premanufacture_concentrate: false, any_premanufacture: true };
  if (m.includes("manufacture_all_feeds")) return preview;
  if (m.includes("set_herd_ration"))
    return { ok: true, changed: true, bom: "B9", per_head_kg: 24, day_kg: 7200, differences: [] };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { FeedDesign } = await import("@/pages/FeedDesign");
const { swapRow } = await import("@/components/feeding/ManualConfig");

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
  call.mockClear();
  window.LIVESTOCK = { bootstrap: { premanufacture_concentrate: true, feed_by_head_count: false } };
});
afterEach(cleanup);

const draw = (ui: React.ReactElement) =>
  render(
    <TooltipProvider>
      <ToastProvider>{ui}</ToastProvider>
    </TooltipProvider>,
  );

async function loadHerd(name: string) {
  fireEvent.click(screen.getAllByRole("combobox")[0]);
  fireEvent.click(await screen.findByRole("option", { name }));
}

function savedLines() {
  const sent = call.mock.calls.find(([m]) => String(m).includes("set_herd_ration"));
  const args = sent?.[1] as { payload: { lines: unknown[] } } | undefined;
  return args?.payload.lines;
}

describe("Feed Design, Mutara's way", () => {
  it("loads a dose as a dose and saves it with its unit, outside the kilos", async () => {
    draw(<FeedDesign />);
    await screen.findByText("Maize Silage");
    await loadHerd("Finishers");
    expect(await screen.findByLabelText("Dose (g a head)")).toBeTruthy();
    expect(screen.getByText(/2\.1 kg for the herd/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Save as the Finishers ration/ }));
    await waitFor(() => expect(savedLines()).toBeTruthy());
    expect(savedLines()).toEqual([
      { item_code: "silage", qty: 15 },
      { item_code: "germ", qty: 5 },
      { item_code: "dv", qty: 7, dose_uom: "Gram" },
    ]);
  });

  it("in percentage mode, changing kg per head rescales every kilogram line", async () => {
    draw(<FeedDesign />);
    await screen.findByText("Maize Silage");
    await loadHerd("Finishers");
    fireEvent.click(await screen.findByRole("button", { name: "% of intake" }));
    const perHead = await screen.findByLabelText("Kg per head per day");
    expect((perHead as HTMLInputElement).value).toBe("20");
    expect(screen.getAllByLabelText("Share (%)").map((e) => (e as HTMLInputElement).value)).toEqual(["75", "25"]);
    fireEvent.change(perHead, { target: { value: "24" } });
    fireEvent.click(screen.getByRole("button", { name: /Save as the Finishers ration/ }));
    await waitFor(() => expect(savedLines()).toBeTruthy());
    expect(savedLines()).toEqual([
      { item_code: "silage", qty: 18 },
      { item_code: "germ", qty: 6 },
      { item_code: "dv", qty: 7, dose_uom: "Gram" },
    ]);
  });

  it("a herd on Mix from raw is offered raw feeds only, one on Pre-manufacture its concentrate too", async () => {
    draw(<FeedDesign />);
    await screen.findByText("Maize Silage");
    // Nothing chosen: some herd still eats a concentrate, so it is offered.
    expect(screen.getByText("Shoat Meal")).toBeTruthy();
    expect(screen.getByRole("button", { name: "A concentrate" })).toBeTruthy();
    await loadHerd("Finishers");
    await waitFor(() => expect(screen.queryByLabelText("Add Shoat Meal")).toBeNull());
    await loadHerd("Shoat Group 1");
    expect(await screen.findByLabelText("Add Shoat Meal")).toBeTruthy();
  });

  it("Manufacture all, not by head count: suggests, and mixes what is typed", async () => {
    draw(<FeedDesign />);
    await screen.findByText("Maize Silage");
    fireEvent.click(screen.getByRole("button", { name: /Manufacture all/ }));
    const finishers = (await screen.findByLabelText("Total fed to Finishers (kg)")) as HTMLInputElement;
    expect(finishers.value).toBe("6000");
    fireEvent.change(finishers, { target: { value: "5400" } });
    fireEvent.change(screen.getByLabelText("Total fed to Shoat Group 1 (kg)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Mix them all" }));
    await waitFor(() =>
      expect(
        call.mock.calls.some(
          ([m, a]) =>
            String(m).includes("manufacture_all_feeds") &&
            (a as { preview: number }).preview === 0 &&
            (a as { totals?: string }).totals === JSON.stringify({ Finishers: 5400 }),
        ),
      ).toBe(true),
    );
  });
});

describe("swapping a forage at the mixer", () => {
  const row = { item_code: "silage", item_name: "Maize Silage", uom: "Kilogram", qty: 10 };

  it("keeps the dry matter and says what it replaced", () => {
    const out = swapRow(row, {
      item_code: "napier", item_name: "Napier", group: "Wet forage", dry_matter_pct: 20, factor: 1.5, reason: null,
    });
    expect(out).toEqual({
      item_code: "napier", item_name: "Napier", uom: "Kilogram", qty: 15, swapped_from: "Maize Silage",
    });
  });

  it("refuses a swap nothing can balance", () => {
    expect(
      swapRow(row, {
        item_code: "sorghum", item_name: "Sorghum", group: "Wet forage", dry_matter_pct: 0, factor: null,
        reason: "no dry matter recorded",
      }),
    ).toBeNull();
  });

  it("swapping back names the original feed", () => {
    const napier = swapRow(row, {
      item_code: "napier", item_name: "Napier", group: "Wet forage", dry_matter_pct: 20, factor: 1.5, reason: null,
    })!;
    const back = swapRow(napier, {
      item_code: "silage", item_name: "Maize Silage", group: "Wet forage", dry_matter_pct: 30, factor: 2 / 3,
      reason: null,
    })!;
    expect(back.qty).toBe(10);
    expect(back.swapped_from).toBe("Maize Silage");
  });
});
