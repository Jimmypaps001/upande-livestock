import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Feeding the way Mutara feeds, on the Feeding page: Manufacture all with the
 * typed group totals of a farm that does not feed by head count, and swapping
 * a forage on dry matter at the mixer.
 *
 * Manufacture all moved here from Feed Design: it moves stock, so it belongs
 * with the other mixing, not with the recipe editor. Percentage mode, doses
 * and the per-herd concentrate setting in the recipe are pinned in
 * ration-editor.test.tsx; the maths in ration-maths.test.ts and Python.
 */

const preview = {
  ok: true, preview: true, date: "2026-11-11", premanufacture_concentrate: false, feed_by_head_count: false,
  concentrates: [],
  herds: [
    { herd: "Finishers", heads: 300, portion: 1, qty: 6000, suggested_qty: 6000, premanufacture: false },
    { herd: "Shoat Group 1", heads: 40, portion: 1, qty: 40, suggested_qty: 40, premanufacture: true },
  ],
  skipped: [],
};

const byHead = {
  ...preview,
  feed_by_head_count: true,
  concentrates: [{ item_code: "sm", item_name: "Shoat Meal", qty: 1000, batches: 1 }],
};

let answer: Record<string, unknown> = preview;
const call = vi.fn(async (method?: string, _args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.includes("posting_day")) return { ok: true, today: "2026-11-11", backdating_open: false };
  if (m.includes("feed_options")) return { ok: true, herds: [] };
  if (m.includes("manufacture_all_feeds")) return answer;
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Feeding } = await import("@/pages/Feeding");
const { swapRow, manualUnitOptions, changeManualUnit } = await import("@/components/feeding/ManualConfig");

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
  answer = preview;
  call.mockClear();
  window.LIVESTOCK = { bootstrap: { premanufacture_concentrate: true, feed_by_head_count: false, roles: [] } };
});
afterEach(cleanup);

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <Feeding />
      </ToastProvider>
    </TooltipProvider>,
  );

const mixed = () =>
  call.mock.calls.find(
    ([m, a]) => String(m).includes("manufacture_all_feeds") && (a as { preview: number }).preview === 0,
  )?.[1] as { totals?: string } | undefined;

describe("Manufacture all, on the Feeding page", () => {
  it("not by head count: previews, suggests, and mixes what is typed", async () => {
    draw();
    fireEvent.click(await screen.findByRole("button", { name: /Manufacture all/ }));
    const finishers = (await screen.findByLabelText("Total fed to Finishers (kg)")) as HTMLInputElement;
    expect(finishers.value).toBe("6000");
    // Nothing is mixed by opening it: the first call is a preview.
    expect(mixed()).toBeUndefined();
    fireEvent.change(finishers, { target: { value: "5400" } });
    fireEvent.change(screen.getByLabelText("Total fed to Shoat Group 1 (kg)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Mix them all" }));
    await waitFor(() => expect(mixed()).toBeTruthy());
    expect(mixed()!.totals).toBe(JSON.stringify({ Finishers: 5400 }));
  });

  it("by head count: lists the concentrates mixed first and sends no totals", async () => {
    answer = byHead;
    draw();
    fireEvent.click(await screen.findByRole("button", { name: /Manufacture all/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Concentrates mixed first")).toBeTruthy();
    expect(dialog.textContent).toMatch(/Shoat Meal: [\d,.]+ kg \(1 batch\)/);
    expect(within(dialog).queryByLabelText("Total fed to Finishers (kg)")).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Mix them all" }));
    await waitFor(() => expect(mixed()).toBeTruthy());
    expect(mixed()!.totals).toBeUndefined();
  });

  it("is not offered to a user who cannot mix", async () => {
    window.LIVESTOCK = { bootstrap: { roles: ["Livestock Nutritionist"] } };
    draw();
    await screen.findByRole("heading", { name: "Feeding" });
    expect(screen.queryByRole("button", { name: /Manufacture all/ })).toBeNull();
  });

  it("points recipe changes at the Ration Editor", async () => {
    draw();
    expect((await screen.findByRole("link", { name: "Ration Editor" })).getAttribute("href")).toBe(
      "#/ration-editor",
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

describe("a manual line in the store's unit", () => {
  const units = {
    molasses: { stock_uom: "Litre", uoms: [{ uom: "Litre", factor: 1, kg: 1.4 }, { uom: "Kg", factor: 0.714, kg: 1 }] },
    hay: { stock_uom: "BALE", uoms: [{ uom: "BALE", factor: 1, kg: 1 / 0.07 }] },
  };

  it("offers kilos under the name the line already uses, and the store's units", () => {
    expect(manualUnitOptions(units, { item_code: "molasses", uom: "Kg" })).toEqual(["Kg", "Litre"]);
    expect(manualUnitOptions(units, { item_code: "hay", uom: "Kilogram" })).toEqual(["Kilogram", "BALE"]);
  });

  it("keeps the kilos when the unit changes", () => {
    const row = { item_code: "molasses", item_name: "Molasses", uom: "Kg", qty: 4.2 };
    expect(changeManualUnit(units, row, "Litre")).toEqual({ ...row, uom: "Litre", qty: 3 });
  });

  it("changes only the unit where nothing gives its kilos", () => {
    const row = { item_code: "x", item_name: "X", uom: "Kg", qty: 2 };
    expect(changeManualUnit(units, row, "Drum")).toEqual({ ...row, uom: "Drum", qty: 2 });
  });
});
