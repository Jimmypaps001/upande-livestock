import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/** The weighing settings arrive through the doctype meta like any Int timing. */

const field = (fieldname: string, label: string) => ({
  fieldname, label, fieldtype: "Int", options: null, description: null, default: null,
  depends_on: null, reqd: false, zero: null, posts: false,
});

const meta = {
  ok: true,
  doctype: "Livestock Settings",
  can_write: true,
  tabs: [{
    fieldname: "tab_weights", label: "Weights",
    sections: [{
      fieldname: "sec_w", label: "Weighing", description: null, tables: [],
      fields: [field("weighing_interval_days", "Weighing interval (days)"), field("weighing_grace_days", "Weighing grace (days)")],
    }],
  }],
  values: { weighing_interval_days: 30, weighing_grace_days: 5 },
  tables: [],
};

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.endsWith("save_livestock_settings")) {
    return { ok: true, changed: { weighing_interval_days: { from: 30, to: 45 } }, unchanged: [],
      values: { weighing_interval_days: 45, weighing_grace_days: 5 } };
  }
  if (m.endsWith("livestock_settings")) return meta;
  void args;
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});
vi.mock("@/components/settings/StockRulesCard", () => ({ StockRulesCard: () => null }));

const { Settings } = await import("@/pages/Settings");

describe("weighing settings page", () => {
  it("renders interval and grace and saves only the one that changed", async () => {
    render(<Settings />);
    const interval = (await screen.findByLabelText("Weighing interval (days)")) as HTMLInputElement;
    expect(interval.value).toBe("30");
    expect((screen.getByLabelText("Weighing grace (days)") as HTMLInputElement).value).toBe("5");

    fireEvent.change(interval, { target: { value: "45" } });
    fireEvent.click(screen.getByRole("button", { name: /Save 1 change/ }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        expect.stringContaining("save_livestock_settings"),
        { payload: { weighing_interval_days: "45" } },
      ),
    );
  });
});
