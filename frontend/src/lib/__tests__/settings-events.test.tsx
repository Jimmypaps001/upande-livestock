import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Settings → Events: every event type with its Enabled switch. Its details —
 * uses stock (and from which groups) and how often (the timings that govern
 * it) — are shown and editable only while it is on.
 */

const field = (fieldname: string, label: string) => ({
  fieldname, label, fieldtype: "Int", options: null, description: null, default: null,
  depends_on: null, reqd: false, zero: "invalid" as const, posts: false,
});

const FIELDS = [
  field("pregnancy_check_days_after_service", "Pregnancy Check Due (days after service)"),
  field("min_vaccination_interval_days", "Min Vaccination Interval (Days)"),
];
const VALUES = { pregnancy_check_days_after_service: 35, min_vaccination_interval_days: 21 };

const rules = () => [
  { event_type: "Feeding", enabled: true, posts_stock_entry: false, item_groups: [], default_store: null,
    must_name_item: false, timings: [] },
  { event_type: "Pregnancy Diagnosis", enabled: false, posts_stock_entry: true, item_groups: ["Gloves"],
    default_store: null, must_name_item: false, timings: ["pregnancy_check_days_after_service"] },
  { event_type: "Vaccination", enabled: true, posts_stock_entry: true, item_groups: ["DRUGS"],
    default_store: null, must_name_item: false, timings: ["min_vaccination_interval_days"] },
];

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.endsWith("save_stock_rules")) {
    const sent = (args?.payload as { rules: { event_type: string }[] }).rules;
    return { ok: true, changed: sent.map((r) => r.event_type), rules: rules() };
  }
  if (m.endsWith("save_livestock_settings")) {
    return { ok: true, changed: { min_vaccination_interval_days: { from: 21, to: 28 } }, unchanged: [],
      values: { ...VALUES, min_vaccination_interval_days: 28 } };
  }
  if (m.endsWith("stock_rules")) return { ok: true, rules: rules(), item_groups: [], stores: [] };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});
vi.mock("@/components/settings/LinkPicker", () => ({ LinkPicker: () => null }));

const { EventsCard } = await import("@/components/settings/EventsCard");
const { detailsShown, ruleProblem, ruleSummary, sameRule } = await import("@/lib/stock-rules");

function show(onSettingsSaved = vi.fn()) {
  render(<EventsCard canWrite fields={FIELDS} values={VALUES} onSettingsSaved={onSettingsSaved} />);
  return onSettingsSaved;
}

const row = (name: string) => screen.getByRole("region", { name });

beforeEach(() => call.mockClear());

describe("Settings → Events", () => {
  it("lists every event type with its Enabled switch, off ones included", async () => {
    show();
    await screen.findByRole("region", { name: "Vaccination" });
    for (const name of ["Feeding", "Pregnancy Diagnosis", "Vaccination"]) {
      expect(screen.getByRole("switch", { name: `${name} enabled` })).toBeTruthy();
    }
    expect(screen.getByRole("switch", { name: "Pregnancy Diagnosis enabled" }).getAttribute("aria-checked")).toBe("false");
  });

  it("shows an enabled event's stock and how-often, and hides a disabled one's", async () => {
    show();
    const vac = await screen.findByRole("region", { name: "Vaccination" });
    expect(within(vac).getByText("Uses stock")).toBeTruthy();
    expect(within(vac).getByText("DRUGS")).toBeTruthy();
    expect(within(vac).getByText("How often")).toBeTruthy();
    expect((within(vac).getByLabelText("Min Vaccination Interval (Days)") as HTMLInputElement).value).toBe("21");

    const pd = row("Pregnancy Diagnosis");
    expect(pd.getAttribute("data-enabled")).toBe("false");
    expect(within(pd).queryByText("Uses stock")).toBeNull();
    expect(within(pd).queryByText("How often")).toBeNull();
    expect(within(pd).queryByLabelText("Pregnancy Check Due (days after service)")).toBeNull();
    expect(within(pd).getByText(/Switched off/)).toBeTruthy();
  });

  it("an event with no due rule says so", async () => {
    show();
    const feeding = await screen.findByRole("region", { name: "Feeding" });
    expect(within(feeding).getByText(/no due rule/)).toBeTruthy();
  });

  it("switching an event on opens its details; switching off folds them", async () => {
    show();
    await screen.findByRole("region", { name: "Pregnancy Diagnosis" });
    fireEvent.click(screen.getByRole("switch", { name: "Pregnancy Diagnosis enabled" }));
    const pd = row("Pregnancy Diagnosis");
    expect(within(pd).getByText("Gloves")).toBeTruthy();
    expect(within(pd).getByLabelText("Pregnancy Check Due (days after service)")).toBeTruthy();

    fireEvent.click(screen.getByRole("switch", { name: "Vaccination enabled" }));
    expect(within(row("Vaccination")).queryByText("How often")).toBeNull();
  });

  it("saves the switch onto the event type and a timing as the setting it is", async () => {
    const onSaved = show();
    await screen.findByRole("region", { name: "Vaccination" });
    fireEvent.change(screen.getByLabelText("Min Vaccination Interval (Days)"), { target: { value: "28" } });
    fireEvent.click(screen.getByRole("switch", { name: "Pregnancy Diagnosis enabled" }));
    fireEvent.click(screen.getByRole("button", { name: "Save events" }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        expect.stringContaining("save_livestock_settings"),
        { payload: { min_vaccination_interval_days: "28" } },
      ),
    );
    const stockCall = call.mock.calls.find(([m]) => String(m).endsWith("save_stock_rules"));
    const sent = (stockCall?.[1]?.payload as { rules: { event_type: string; enabled: boolean }[] }).rules;
    expect(sent).toEqual([expect.objectContaining({ event_type: "Pregnancy Diagnosis", enabled: true })]);
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ min_vaccination_interval_days: 28 })));
  });

  it("a timing typed under an event then switched off is not sent", async () => {
    show();
    await screen.findByRole("region", { name: "Vaccination" });
    fireEvent.change(screen.getByLabelText("Min Vaccination Interval (Days)"), { target: { value: "28" } });
    fireEvent.click(screen.getByRole("switch", { name: "Vaccination enabled" }));
    fireEvent.click(screen.getByRole("button", { name: "Save events" }));
    await waitFor(() => expect(call.mock.calls.some(([m]) => String(m).endsWith("save_stock_rules"))).toBe(true));
    expect(call.mock.calls.some(([m]) => String(m).endsWith("save_livestock_settings"))).toBe(false);
  });
});

describe("the rule helpers", () => {
  const base = rules()[2];
  it("details show only while enabled; a switched-off rule is not checked", () => {
    expect(detailsShown(base)).toBe(true);
    expect(detailsShown({ ...base, enabled: false })).toBe(false);
    expect(ruleProblem({ ...base, item_groups: [] })).toMatch(/item group/);
    expect(ruleProblem({ ...base, enabled: false, item_groups: [] })).toBeNull();
  });
  it("the switch is part of the rule, and the summary says when it is off", () => {
    expect(sameRule(base, { ...base, enabled: false })).toBe(false);
    expect(ruleSummary({ ...base, enabled: false })).toMatch(/Switched off/);
    expect(ruleSummary(base)).toMatch(/Uses stock from DRUGS/);
  });
});
