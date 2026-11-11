import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/** The birth window and its retro-diagnosis switch arrive through the doctype meta, like any setting. */

const field = (fieldname: string, label: string, fieldtype = "Int") => ({
  fieldname, label, fieldtype, options: null, description: null, default: null,
  depends_on: null, reqd: false, zero: null, posts: false,
});

const meta = {
  ok: true,
  doctype: "Livestock Settings",
  can_write: true,
  tabs: [{
    fieldname: "general_tab", label: "General",
    sections: [{
      fieldname: "sb_birth_window", label: "Birth Window", description: null, tables: [],
      fields: [
        field("gestation_window_min_days", "Gestation Window Minimum (days)"),
        field("gestation_window_max_days", "Gestation Window Maximum (days)"),
        field("allow_retro_pregnancy_diagnosis", "Allow pregnancy diagnosis when back-recording a service", "Check"),
      ],
    }],
  }],
  values: { gestation_window_min_days: 270, gestation_window_max_days: 295, allow_retro_pregnancy_diagnosis: 1 },
  tables: [],
};

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.endsWith("save_livestock_settings")) {
    return { ok: true, changed: { gestation_window_max_days: { from: 295, to: 300 } }, unchanged: [],
      values: { gestation_window_min_days: 270, gestation_window_max_days: 300, allow_retro_pregnancy_diagnosis: 1 } };
  }
  if (m.endsWith("livestock_settings")) return meta;
  void args;
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});
vi.mock("@/components/settings/EventsCard", () => ({ EventsCard: () => null }));

const { Settings } = await import("@/pages/Settings");

describe("birth window settings", () => {
  it("shows the window and the switch, and saves only what changed", async () => {
    render(<Settings />);
    const max = (await screen.findByLabelText("Gestation Window Maximum (days)")) as HTMLInputElement;
    expect(max.value).toBe("295");
    expect((screen.getByLabelText("Gestation Window Minimum (days)") as HTMLInputElement).value).toBe("270");
    expect(screen.getByText("Allow pregnancy diagnosis when back-recording a service")).toBeTruthy();
    fireEvent.change(max, { target: { value: "300" } });
    fireEvent.click(screen.getByRole("button", { name: /Save 1 change/ }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        expect.stringContaining("save_livestock_settings"),
        { payload: { gestation_window_max_days: "300" } },
      ),
    );
  });
});
