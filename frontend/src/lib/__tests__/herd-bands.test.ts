import { describe, expect, it } from "vitest";
import { bandPayload, emptyDetails, showsBandFields, validateBand, withClass, type HerdDetails } from "@/lib/herds";
import { changePayload, pendingChanges, type SettingsField, type SettingsValue } from "@/lib/settings";

describe("band fields", () => {
  it("are shown only for Fattening and Calf herds", () => {
    expect(showsBandFields("Fattening")).toBe(true);
    expect(showsBandFields("Calf")).toBe(true);
    for (const c of ["Breeding", "Cow", "Other"] as const) expect(showsBandFields(c)).toBe(false);
  });

  it("clears the old band (explicit 0/0) when the class has none, keeping the target as entered", () => {
    const d: HerdDetails = {
      herd_class: "Breeding", min_weight_kg: "300", max_weight_kg: "400", target_adg_kg: "0.9", weigh_monthly: true, weigh_touched: true,
    };
    expect(bandPayload(d)).toEqual({
      herd_class: "Breeding", weigh_monthly: 1, min_weight_kg: 0, max_weight_kg: 0, target_adg_kg: 0.9,
    });
  });

  it("sends numbers for a Fattening herd, blank max as 0 (open-ended)", () => {
    const d: HerdDetails = {
      herd_class: "Fattening", min_weight_kg: "300", max_weight_kg: "", target_adg_kg: "0.9", weigh_monthly: false, weigh_touched: true,
    };
    expect(bandPayload(d)).toEqual({
      herd_class: "Fattening", min_weight_kg: 300, max_weight_kg: 0, target_adg_kg: 0.9, weigh_monthly: 0,
    });
  });

  it("ticks weigh_monthly when the class becomes Fattening or Breeding, and sends it then", () => {
    for (const c of ["Fattening", "Breeding"] as const) {
      const d = withClass(emptyDetails(), c);
      expect(d.weigh_monthly).toBe(true);
      expect(bandPayload(d).weigh_monthly).toBe(1);
      // The person may untick it, and that is sent as an explicit off.
      expect(bandPayload({ ...d, weigh_monthly: false }).weigh_monthly).toBe(0);
    }
  });

  it("leaves weigh_monthly out of the payload until it is touched", () => {
    expect("weigh_monthly" in bandPayload(emptyDetails())).toBe(false);
    expect("weigh_monthly" in bandPayload(withClass(emptyDetails(), "Other"))).toBe(false);
  });

  it("refuses a max that is not above the min", () => {
    const d: HerdDetails = {
      herd_class: "Fattening", min_weight_kg: "400", max_weight_kg: "300", target_adg_kg: "", weigh_monthly: true,
    };
    expect(validateBand(d)).toMatch(/above/);
  });
});

describe("weighing settings", () => {
  const f = (fieldname: string): SettingsField => ({
    fieldname, label: fieldname, fieldtype: "Int", options: null, description: null, default: null,
    depends_on: null, reqd: false, zero: null, posts: false,
  });
  const fields = [f("weighing_interval_days"), f("weighing_grace_days")];
  const values: Record<string, SettingsValue> = { weighing_interval_days: 30, weighing_grace_days: 5 };

  it("saves interval and grace through the settings API payload, only when changed", () => {
    const changes = pendingChanges(fields, values, { weighing_interval_days: "45", weighing_grace_days: "5" });
    expect(changePayload(changes)).toEqual({ weighing_interval_days: "45" });
  });
});
