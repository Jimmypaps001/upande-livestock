import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/** The feedlot weight bands are editable from Settings, through the Herds' own ladder editor. */

const meta = {
  ok: true, doctype: "Livestock Settings", can_write: true, tabs: [], values: {}, tables: [],
};

const call = vi.fn(async (method?: string) => {
  const m = method || "";
  if (m.endsWith("herd_rations")) {
    return {
      ok: true,
      herds: [
        { herd: "Starters", herd_class: "Fattening", min_weight_kg: 0, max_weight_kg: 250, target_adg_kg: 0.9, weigh_monthly: 1 },
        { herd: "Growers", herd_class: "Fattening", min_weight_kg: 250, max_weight_kg: 280, target_adg_kg: 0.9, weigh_monthly: 1 },
        { herd: "Finishers", herd_class: "Fattening", min_weight_kg: 280, max_weight_kg: 0, target_adg_kg: 0.9, weigh_monthly: 1 },
        { herd: "Lactation Group 1", herd_class: "Breeding", min_weight_kg: 0, max_weight_kg: 0, weigh_monthly: 1 },
      ],
    };
  }
  if (m.endsWith("livestock_settings")) return meta;
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});
vi.mock("@/components/settings/StockRulesCard", () => ({ StockRulesCard: () => null }));

const { Settings } = await import("@/pages/Settings");

describe("settings page: feedlot bands", () => {
  it("lists the three Fattening herds as editable bands and leaves breeding herds out", async () => {
    render(<Settings />);
    await waitFor(() => expect(screen.getAllByDisplayValue("250").length).toBeGreaterThan(0));
    expect(screen.getByText("Starters")).toBeTruthy();
    expect(screen.getByText("Growers")).toBeTruthy();
    expect(screen.getByText("Finishers")).toBeTruthy();
    expect(screen.queryByText("Lactation Group 1")).toBeNull();
  });
});
