import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Feed Design, the nutrition panel and the Pre-manufacture Concentrate switch.
 *
 * The page sends facts and draws answers: nothing here checks a nutrition
 * figure's arithmetic (that is the server's, tested in Python), only that the
 * page asks, shows what comes back including the missing-data warning, offers
 * raw feeds only when the switch is off, and hides the Concentrate nav entry.
 */

const library = {
  ok: true,
  premanufacture_concentrate: true,
  feeds: [
    { item_code: "bran", item_name: "Wheat Bran", category: "Energy (grain / by-product)", is_made: false,
      recorded: true, has_data: true, nutrient_source: "Book value", dry_matter_pct: 89, cp_pct: 16,
      carbohydrate_pct: 25, ndf_pct: 42, fat_pct: 4, me_mj_per_kg: 11.5 },
    { item_code: "meal", item_name: "Finisher Meal", category: "Concentrate (made)", is_made: true,
      computed: true, recorded: false, has_data: true, nutrient_source: null, dry_matter_pct: 88, cp_pct: 14,
      carbohydrate_pct: 30, ndf_pct: 30, fat_pct: 4, me_mj_per_kg: 11 },
  ],
  undescribed: [{ item_code: "ghost", item_name: "Ghost Feed", has_data: false }],
};

const nutrition = {
  ok: true, as_fed_kg: 4, dm_kg: 3.6, dm_pct: 90, cp_pct: 16, carbohydrate_pct: 25, ndf_pct: 42,
  fat_pct: 4, me_mj_per_kg: 11.5, me_mj_total: 41.4, ca_pct: 0.1, p_pct: 1, cost: 160,
  cost_per_kg_as_fed: 40, cost_per_kg_dm: 44, unpriced: [], lines: [],
  missing: [{ item_code: "ghost", item_name: "Ghost Feed", reason: "no Livestock Feed record",
              fields: [], qty_kg: 1, via: null }],
};

const herds = [{ herd: "Finishers", heads: 10, bom: "B1", ration_item: "Ration - Finishers",
  ration_name: "Ration - Finishers", per_head_kg: 3, day_kg: 30, lines_total: 3, balanced: true,
  lines: [{ item_code: "meal", item_name: "Finisher Meal", qty: 3, uom: "Kg" }] }];

let on = true;
const call = vi.fn(async (method?: string, _args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.includes("livestock_feeds")) return { ...library, premanufacture_concentrate: on };
  if (m.includes("feed_nutrition")) return nutrition;
  if (m.includes("herd_rations")) return { ok: true, herds, feeds: [], premanufacture_concentrate: on };
  if (m.includes("expand_concentrates"))
    return { ok: true, expanded: ["meal"], lines: [{ item_code: "bran", item_name: "Wheat Bran", qty: 3 }] };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { FeedDesign } = await import("@/pages/FeedDesign");
const { Concentrate } = await import("@/pages/Concentrate");

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
});

beforeEach(() => {
  on = true;
  call.mockClear();
  window.LIVESTOCK = { bootstrap: { premanufacture_concentrate: true } };
});
afterEach(cleanup);

const draw = (ui: React.ReactElement) =>
  render(
    <TooltipProvider>
      <ToastProvider>{ui}</ToastProvider>
    </TooltipProvider>,
  );

describe("Feed Design", () => {
  it("lists the library with a no-data badge for an undescribed feed", async () => {
    draw(<FeedDesign />);
    await screen.findByText("Wheat Bran");
    expect(screen.getByText("Ghost Feed")).toBeTruthy();
    expect(screen.getAllByText("no data").length).toBeGreaterThan(0);
  });

  it("asks the server for the nutrition once lines are in, and says what is missing", async () => {
    draw(<FeedDesign />);
    await screen.findByText("Wheat Bran");
    fireEvent.click(screen.getByLabelText("Add Wheat Bran"));
    const qty = await screen.findByLabelText("Amount (kg)");
    fireEvent.change(qty, { target: { value: "4" } });
    await waitFor(
      () =>
        expect(
          call.mock.calls.some(
            ([m, a]) =>
              String(m).includes("feed_nutrition.feed_nutrition") &&
              String((a as { lines: string } | undefined)?.lines).includes('"qty":4'),
          ),
        ).toBe(true),
      { timeout: 2000 },
    );
    expect(await screen.findByText(/No nutrient data for/)).toBeTruthy();
    expect(screen.getByText("Crude protein")).toBeTruthy();
  });

  it("offers raw feeds only when the switch is off, and offers to expand a concentrate", async () => {
    on = false;
    window.LIVESTOCK = { bootstrap: { premanufacture_concentrate: false } };
    draw(<FeedDesign />);
    await screen.findByText("Wheat Bran");
    expect(screen.queryByText("Finisher Meal")).toBeNull();
    // Load the herd whose ration still names the concentrate.
    fireEvent.click(screen.getAllByRole("combobox")[0]);
    fireEvent.click(await screen.findByRole("option", { name: "Finishers" }));
    const expand = await screen.findByRole("button", { name: /Expand into ingredients/ });
    fireEvent.click(expand);
    await waitFor(() =>
      expect(call.mock.calls.some(([m]) => String(m).includes("expand_concentrates"))).toBe(true),
    );
  });

  it("hides the design-a-concentrate choice when the switch is off", async () => {
    on = false;
    draw(<FeedDesign />);
    await screen.findByText("Wheat Bran");
    expect(screen.queryByRole("button", { name: "A concentrate" })).toBeNull();
  });
});

describe("the Concentrate page with the switch off", () => {
  it("says it is not used instead of offering to mix", () => {
    window.LIVESTOCK = { bootstrap: { premanufacture_concentrate: false } };
    draw(<Concentrate />);
    expect(screen.getByText(/does not pre-manufacture concentrate/)).toBeTruthy();
    expect(screen.queryByText("New concentrate")).toBeNull();
  });
});
