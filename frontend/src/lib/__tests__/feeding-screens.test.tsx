import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Which feeding screen does what, and when the Concentrate one exists.
 *
 * The farm said the feeding screens repeated each other. Now: recipes are
 * written in the Ration Editor only (Feed Design is gone, its old link
 * redirects), feed is mixed on Feeding, and a concentrate batch is mixed on
 * Concentrate — a window shown, exactly once, only where some herd eats a
 * pre-made concentrate.
 */

const shoatMeal = {
  item_code: "shoat meal", item_name: "Shoat Meal", bom_no: "BOM-SM-1", base_qty: 1000, uom: "Kilogram",
  mix_qty: 1000, in_store: 0, stores: [],
  lines: [{ item_code: "germ", item_name: "Maize Germ", recipe_qty: 1000, recipe_uom: "Kilogram",
            required_qty: 1000, uom: "Kilogram", available: 5000, available_elsewhere: 0, short_qty: 0,
            source_warehouse: "Feed Store" }],
};

const call = vi.fn(async (method?: string, _args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.includes("concentrates.concentrates"))
    return { ok: true, concentrates: [shoatMeal], warehouses: ["Feed Store"], default_target: "Feed Store" };
  if (m.includes("update_herd")) return { ok: true, herd: "Shoat Group 1", concentrate_mode: "Pre-manufacture" };
  return { ok: true, lines: [] };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { ALIASES, hashParams, isView, redirectHash, viewOfHash } = await import("@/lib/router");
const { NAV, visibleNav } = await import("@/components/AppSidebar");
const { viewOpen } = await import("@/lib/roles");
const { Concentrate, concentrateRecipeHref } = await import("@/pages/Concentrate");
const { ConcentrateByHerd } = await import("@/components/herds/ConcentrateByHerd");
const { resolvePremanufacture } = await import("@/lib/herds");

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
  window.LIVESTOCK = { bootstrap: { premanufacture_concentrate: true, roles: [] } };
});
afterEach(cleanup);

const draw = (ui: React.ReactElement) =>
  render(
    <TooltipProvider>
      <ToastProvider>{ui}</ToastProvider>
    </TooltipProvider>,
  );

describe("the old Feed Design route", () => {
  it("is no longer a screen of its own", () => {
    expect(isView("feed-design")).toBe(false);
    expect(ALIASES["feed-design"]).toBe("ration-editor");
  });

  it("opens the Ration Editor, and is rewritten so Back does not bounce through it", () => {
    expect(viewOfHash("#/feed-design")).toBe("ration-editor");
    expect(viewOfHash("#/Feed-Design")).toBe("ration-editor");
    expect(redirectHash("#/feed-design")).toBe("#/ration-editor");
    expect(redirectHash("#/feed-design?herd=Finishers")).toBe("#/ration-editor?herd=Finishers");
    expect(redirectHash("#/ration-editor")).toBeNull();
    expect(redirectHash("#/feeding")).toBeNull();
  });

  it("leaves every other route alone", () => {
    expect(viewOfHash("#/concentrate")).toBe("concentrate");
    expect(viewOfHash("#/nowhere")).toBe("feeding");
    expect(viewOfHash("")).toBe("feeding");
  });

  it("carries what the link asks for", () => {
    expect(hashParams("#/ration-editor?concentrate=shoat%20meal").get("concentrate")).toBe("shoat meal");
    expect(hashParams("#/ration-editor").get("concentrate")).toBeNull();
  });
});

describe("the feeding section of the sidebar", () => {
  const feedingSection = (open: (v: Parameters<typeof viewOpen>[0]) => boolean) =>
    visibleNav(open).find((s) => s.label === "Feeding")!.items.map((i) => i.label);

  it("has one recipe screen, named Ration Editor, and no Feed Design", () => {
    const all = NAV.flatMap((s) => s.items);
    expect(all.filter((i) => i.view === "ration-editor").map((i) => i.label)).toEqual(["Ration Editor"]);
    expect(all.some((i) => /feed design/i.test(i.label))).toBe(false);
  });

  it("shows Concentrate exactly once where concentrate is in use", () => {
    const items = feedingSection((v) => viewOpen(v, ["Livestock Manager"], true));
    expect(items.filter((l) => l === "Concentrate")).toHaveLength(1);
    expect(items).toEqual(["Feeding", "Ration Editor", "Concentrate", "Feed in Store", "Ration History", "Procurement"]);
  });

  it("hides Concentrate where no herd eats a pre-made one", () => {
    const items = feedingSection((v) => viewOpen(v, ["Livestock Manager"], false));
    expect(items).not.toContain("Concentrate");
    expect(items).toContain("Ration Editor");
  });

  it("shows a nutritionist-only user the feed screens alone", () => {
    const sections = visibleNav((v) => viewOpen(v, ["Livestock Nutritionist"], true));
    expect(sections.map((s) => s.label)).toEqual(["Feeding"]);
    expect(sections[0].items.map((i) => i.view)).toEqual(["ration-editor", "concentrate", "stock", "rations"]);
  });
});

describe("the Concentrate window", () => {
  it("mixes batches and leaves the recipe to the Ration Editor", async () => {
    draw(<Concentrate />);
    await screen.findByText("Shoat Meal");
    expect(screen.getByRole("button", { name: "Mix" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Recipe" }).getAttribute("href")).toBe(
      "#/ration-editor?concentrate=shoat%20meal",
    );
    expect(screen.getByRole("link", { name: "New concentrate" }).getAttribute("href")).toBe(
      "#/ration-editor?concentrate=new",
    );
    // No second recipe editor on this page.
    expect(screen.queryByText("Save recipe")).toBeNull();
    expect(screen.queryByLabelText("Concentrate name")).toBeNull();
    expect(call.mock.calls.some(([m]) => String(m).includes("herd_rations"))).toBe(false);
  });

  it("says it is not used where no herd eats a pre-made concentrate", () => {
    window.LIVESTOCK = { bootstrap: { premanufacture_concentrate: false } };
    draw(<Concentrate />);
    expect(screen.getByText(/No herd on this farm eats a pre-made concentrate/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mix" })).toBeNull();
  });

  it("links a new recipe to the editor", () => {
    expect(concentrateRecipeHref(null)).toBe("#/ration-editor?concentrate=new");
  });
});

describe("the per-herd Concentrate setting on Herds", () => {
  it("follows the farm on Farm default and overrides it otherwise", () => {
    expect(resolvePremanufacture("Farm default", true)).toBe(true);
    expect(resolvePremanufacture(undefined, false)).toBe(false);
    expect(resolvePremanufacture("Pre-manufacture", false)).toBe(true);
    expect(resolvePremanufacture("Mix from raw", true)).toBe(false);
  });

  it("shows what each herd does and whether the window is shown", () => {
    draw(
      <ConcentrateByHerd
        farmOn={false}
        loading={false}
        onDone={() => {}}
        herds={[
          { herd: "Finishers", concentrate_mode: "Farm default" },
          { herd: "Shoat Group 1", concentrate_mode: "Pre-manufacture" },
        ]}
      />,
    );
    expect(screen.getByText("mixed from raw")).toBeTruthy();
    expect(screen.getByText("pre-made concentrate")).toBeTruthy();
    expect(screen.getByText("shown")).toBeTruthy();
  });

  it("changes one herd's setting through update_herd and nothing else", async () => {
    const done = vi.fn();
    draw(
      <ConcentrateByHerd
        farmOn={false}
        loading={false}
        onDone={done}
        herds={[{ herd: "Shoat Group 1", concentrate_mode: "Farm default" }]}
      />,
    );
    fireEvent.click(screen.getByLabelText("Concentrate for Shoat Group 1"));
    fireEvent.click(await screen.findByRole("option", { name: "Pre-manufacture" }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    const sent = call.mock.calls.find(([m]) => String(m).includes("update_herd"))?.[1];
    expect(sent).toEqual({ herd: "Shoat Group 1", concentrate_mode: "Pre-manufacture" });
  });
});
