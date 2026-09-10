import { describe, expect, it } from "vitest";
import {
  isVisible,
  pendingChanges,
  showValue,
  zeroWarnings,
  type SettingsField,
  type SettingsValue,
} from "@/lib/settings";

function field(over: Partial<SettingsField> & { fieldname: string }): SettingsField {
  return {
    label: over.fieldname,
    fieldtype: "Int",
    options: null,
    description: null,
    default: null,
    depends_on: null,
    reqd: false,
    zero: null,
    posts: false,
    ...over,
  };
}

/** The two fields a 0 legitimately switches off, and one where a 0 is the bug
 *  `repair_zeroed_age_interval_settings` exists to undo. */
const FIELDS: SettingsField[] = [
  field({ fieldname: "post_abortion_min_service_days", zero: "disables" }),
  field({ fieldname: "gestation_period_days", zero: "invalid" }),
  field({ fieldname: "drug_warehouse", fieldtype: "Link", options: "Warehouse", posts: true }),
  field({ fieldname: "cull_bulls_after_birth", fieldtype: "Check" }),
  field({
    fieldname: "bull_cull_max_days",
    depends_on: "cull_bulls_after_birth",
  }),
];

const STORED: Record<string, SettingsValue> = {
  post_abortion_min_service_days: 30,
  gestation_period_days: 280,
  drug_warehouse: "Livestock Drug Store - KR",
  cull_bulls_after_birth: 1,
  bull_cull_max_days: 14,
};

describe("pendingChanges", () => {
  it("sends nothing when nothing was touched", () => {
    expect(pendingChanges(FIELDS, STORED, {})).toEqual([]);
  });

  it("does not send a number the box merely re-typed as text", () => {
    // The input hands back "280"; the server said 280. Re-sending every field
    // that looks different as a string is how a one-field edit becomes a
    // fifty-field write.
    expect(pendingChanges(FIELDS, STORED, { gestation_period_days: "280" })).toEqual([]);
  });

  it("sends only the field that actually changed", () => {
    const changes = pendingChanges(FIELDS, STORED, {
      gestation_period_days: "281",
      drug_warehouse: "Livestock Drug Store - KR",
    });
    expect(changes.map((c) => c.field.fieldname)).toEqual(["gestation_period_days"]);
    expect(changes[0].from).toBe(280);
    expect(changes[0].to).toBe("281");
  });

  it("treats an emptied number box as a change, so the server can refuse it in its own words", () => {
    const changes = pendingChanges(FIELDS, STORED, { gestation_period_days: "" });
    expect(changes).toHaveLength(1);
  });

  it("never treats 0 as an untouched field", () => {
    const changes = pendingChanges(FIELDS, STORED, { post_abortion_min_service_days: 0 });
    expect(changes.map((c) => c.field.fieldname)).toEqual(["post_abortion_min_service_days"]);
  });

  it("ignores a fieldname the doctype does not have", () => {
    expect(pendingChanges(FIELDS, STORED, { not_a_field: 1 })).toEqual([]);
  });
});

describe("zeroWarnings", () => {
  it("says nothing while every rule holds a real value", () => {
    expect(zeroWarnings(FIELDS, STORED, {})).toEqual([]);
  });

  it("warns on a typed 0 that switches a rule off", () => {
    const warnings = zeroWarnings(FIELDS, STORED, { post_abortion_min_service_days: "0" });
    expect(warnings).toHaveLength(1);
    expect(warnings[0].rule).toBe("disables");
    expect(warnings[0].stored).toBe(false);
  });

  it("warns on a 0 already stored, which is the fault the repair patch undoes", () => {
    const warnings = zeroWarnings(FIELDS, { ...STORED, gestation_period_days: 0 }, {});
    expect(warnings).toHaveLength(1);
    expect(warnings[0].rule).toBe("invalid");
    expect(warnings[0].stored).toBe(true);
  });

  it("does not mistake an unset field for a 0 — one uses the default, the other turns the rule off", () => {
    expect(zeroWarnings(FIELDS, { ...STORED, gestation_period_days: null }, {})).toEqual([]);
  });
});

describe("showValue", () => {
  it("says so when a field has no value, rather than showing a blank", () => {
    expect(showValue(FIELDS[0], null)).toBe("not set");
  });

  it("shows 0 as 0", () => {
    expect(showValue(FIELDS[0], 0)).toBe("0");
  });

  it("reads a tick box as words", () => {
    expect(showValue(FIELDS[3], 1)).toBe("On");
    expect(showValue(FIELDS[3], 0)).toBe("Off");
  });
});

describe("isVisible", () => {
  const dependent = FIELDS[4];

  it("shows a dependent field while its condition holds", () => {
    expect(isVisible(dependent, STORED, {})).toBe(true);
  });

  it("hides it once the condition is unticked in the draft", () => {
    expect(isVisible(dependent, STORED, { cull_bulls_after_birth: 0 })).toBe(false);
  });

  it("shows a field whose depends_on it cannot evaluate rather than hiding it", () => {
    const evalled = field({ fieldname: "x", depends_on: "eval:doc.something > 1" });
    expect(isVisible(evalled, STORED, {})).toBe(true);
  });
});
