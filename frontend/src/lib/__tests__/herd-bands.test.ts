import { describe, expect, it } from "vitest";
import { bandPayload, showsBandFields, validateBand, type HerdDetails } from "@/lib/herds";
import { changePayload, pendingChanges, type SettingsField, type SettingsValue } from "@/lib/settings";

describe("band fields", () => {
  it("are shown only for Fattening and Calf herds", () => {
    expect(showsBandFields("Fattening")).toBe(true);
    expect(showsBandFields("Calf")).toBe(true);
    for (const c of ["Breeding", "Cow", "Other"] as const) expect(showsBandFields(c)).toBe(false);
  });

  it("are not sent for a herd whose class has no band", () => {
    const d: HerdDetails = {
      herd_class: "Breeding", min_weight_kg: "300", max_weight_kg: "400", target_adg_kg: "0.9", weigh_monthly: true,
    };
    expect(bandPayload(d)).toEqual({ herd_class: "Breeding", weigh_monthly: 1 });
  });

  it("sends numbers for a Fattening herd, blank max as 0 (open-ended)", () => {
    const d: HerdDetails = {
      herd_class: "Fattening", min_weight_kg: "300", max_weight_kg: "", target_adg_kg: "0.9", weigh_monthly: false,
    };
    expect(bandPayload(d)).toEqual({
      herd_class: "Fattening", min_weight_kg: 300, max_weight_kg: 0, target_adg_kg: 0.9, weigh_monthly: 0,
    });
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
