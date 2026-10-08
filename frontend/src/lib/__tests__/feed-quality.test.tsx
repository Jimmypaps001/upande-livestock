import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Quality & Feed: each milking herd's ration beside its milk quality, set
 * against the other herds, and one figure followed week by week.
 */

const herd = (name: string, fat: number, vsFat: number, scc: number, vsScc: number) => ({
  herd: name,
  cows: 20,
  ration: {
    bom: `BOM-${name}`, name: `${name} ration`, per_head: 30, uom: "Kilogram", concentrate_kg: 8,
    concentrate_share: 0.27,
    lines: [{ item_code: "SIL", item_name: "Silage", qty: 18, uom: "Kilogram", concentrate: false },
            { item_code: "DCM", item_name: "Dairy Meal", qty: 8, uom: "Kilogram", concentrate: true }],
  },
  fed: { runs: 0, kg: 0 },
  quality: { fat, protein: 3.3, scc, readings: 40, milkings: 40, milk_per_cow_day: 16.2 },
  vs_rest: { fat: vsFat, protein: 2.1, scc: vsScc },
});

const state = vi.hoisted(() => ({ asked: [] as number[] }));

const call = vi.fn(async (method?: string, args?: { payload?: { days?: number } }) => {
  if ((method || "").includes("quality_vs_feed")) {
    state.asked.push(args?.payload?.days ?? 0);
    return {
      ok: true, days: args?.payload?.days ?? 90, from_date: "2026-07-11", to_date: "2026-10-08", windows: [30, 90, 150],
      herds: [herd("Lactating group 1", 3.61, -10.6, 255000, 21.6), herd("Test 3", 4.35, 18.7, 167000, -34.5)],
      weeks: [
        { week: "2026-09-28", herds: { "Lactating group 1": { fat: 3.6, protein: 3.2, scc: 250000 }, "Test 3": { fat: 4.5, protein: 3.4, scc: 160000 } } },
        { week: "2026-10-05", herds: { "Lactating group 1": { fat: 3.7, protein: 3.2, scc: 258000 }, "Test 3": { fat: 4.6, protein: 3.4, scc: 175000 } } },
      ],
    };
  }
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { FeedQuality } = await import("@/pages/FeedQuality");

const draw = () => render(<TooltipProvider><FeedQuality /></TooltipProvider>);

beforeEach(() => {
  state.asked = [];
});

describe("Quality & Feed", () => {
  it("puts each herd's ration beside its quality, against the other herds", async () => {
    draw();
    const test3 = await screen.findByLabelText("Test 3");
    expect(within(test3).getByText("Test 3 ration")).toBeTruthy();
    expect(within(test3).getByText(/27% concentrate \(8.00 kg\)/)).toBeTruthy();
    expect(within(test3).getByText("4.35%")).toBeTruthy();
    expect(within(test3).getByText(/\+18.7% vs other herds/)).toBeTruthy();
    // A lower cell count is the better way round, and is said in words.
    const scc = within(test3).getByText(/−34.5% vs other herds/);
    expect(within(scc).getByText("better")).toBeTruthy();
    expect(within(screen.getByLabelText("Lactating group 1")).getAllByText("worse").length).toBeGreaterThan(0);
  });

  it("charts butterfat by week, one line per herd, and switches the figure", async () => {
    draw();
    expect(await screen.findByRole("img", { name: /Butterfat by week/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Somatic cells" }));
    expect(await screen.findByRole("img", { name: /Somatic cells by week/ })).toBeTruthy();
  });

  it("has the same figures as a table", async () => {
    draw();
    await screen.findByLabelText("Test 3");
    fireEvent.click(screen.getByRole("button", { name: "Table" }));
    const table = await screen.findByRole("table", { name: "Butterfat by week" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("4.60%")).toBeTruthy();
  });

  it("asks again for a different window", async () => {
    draw();
    await waitFor(() => expect(state.asked).toEqual([90]));
    fireEvent.click(screen.getByRole("button", { name: "Last 150 days" }));
    await waitFor(() => expect(state.asked).toEqual([90, 150]));
  });
});
