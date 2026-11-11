import { describe, expect, it } from "vitest";
import {
  addDays,
  blankRetro,
  daysBetween,
  fitsWindow,
  needsService,
  pdDateValid,
  retroPayload,
  retroProblems,
  serviceRangeFor,
  type BirthCheck,
} from "@/lib/birth-window";

const check: BirthCheck = {
  dam: "A001/20",
  birth_date: "2026-11-01",
  window: { min_days: 270, max_days: 295 },
  service_from: "2026-01-10",
  service_to: "2026-02-04",
  retro_allowed: true,
  retro_refusal: "",
  is_manager: true,
  backdating_open: false,
  allow_diagnosis: true,
};

describe("the birth window", () => {
  it("adds days across month and year ends", () => {
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(addDays("2025-12-31", 1)).toBe("2026-01-01");
    expect(addDays("nonsense", 3)).toBe("");
  });

  it("gives the service dates that put a birth inside [min, max]", () => {
    expect(serviceRangeFor("2026-11-01", 270, 295)).toEqual({ from: "2026-01-10", to: "2026-02-04" });
    // swapped settings still give the same range
    expect(serviceRangeFor("2026-11-01", 295, 270)).toEqual({ from: "2026-01-10", to: "2026-02-04" });
  });

  it("includes both ends of the window and nothing outside it", () => {
    expect(fitsWindow("2026-01-10", "2026-11-01", 270, 295)).toBe(true);
    expect(fitsWindow("2026-02-04", "2026-11-01", 270, 295)).toBe(true);
    expect(fitsWindow("2026-01-09", "2026-11-01", 270, 295)).toBe(false);
    expect(fitsWindow("2026-02-05", "2026-11-01", 270, 295)).toBe(false);
    expect(fitsWindow("", "2026-11-01", 270, 295)).toBe(false);
  });

  it("puts a diagnosis strictly between the service and the birth", () => {
    expect(pdDateValid("2026-03-15", "2026-01-20", "2026-11-01")).toBe(true);
    expect(pdDateValid("2026-01-20", "2026-01-20", "2026-11-01")).toBe(false);
    expect(pdDateValid("2026-11-01", "2026-01-20", "2026-11-01")).toBe(false);
    expect(pdDateValid("", "2026-01-20", "2026-11-01")).toBe(false);
  });

  it("counts days between two dates", () => {
    expect(daysBetween("2026-01-20", "2026-11-01")).toBe(285);
  });

  it("recognises the server's record-the-service-first refusal", () => {
    expect(needsService({ error: "x", code: "birth_needs_service" })).toBe(true);
    expect(needsService({ error: "x" })).toBe(false);
    expect(needsService(null)).toBe(false);
  });
});

describe("the retro form", () => {
  it("lists what is missing, then nothing once filled", () => {
    const f = blankRetro();
    expect(retroProblems(f, "2026-11-01", check)).toHaveLength(3);
    const ready = { ...f, service_date: "2026-01-20", service_type: "A.I.", herd: "Heifers" };
    expect(retroProblems(ready, "2026-11-01", check)).toEqual([]);
    expect(retroProblems({ ...ready, service_date: "2025-12-01" }, "2026-11-01", check)[0]).toMatch(/between/);
    expect(
      retroProblems({ ...ready, with_diagnosis: true, diagnosis_date: "2026-11-02" }, "2026-11-01", check),
    ).toEqual(["The diagnosis must be dated after the service and before the birth."]);
  });

  it("sends the straw both ways, and the diagnosis only when allowed", () => {
    const f = { ...blankRetro(), service_date: "2026-01-20", service_type: "A.I.", herd: "Heifers",
      straw: "STRAW-1", straw_qty: "2", straw_store: "Fridge", with_diagnosis: true, diagnosis_date: "2026-03-01" };
    const p = retroPayload(f, check);
    expect(p.items).toEqual([{ item_code: "STRAW-1", qty: 2, source_warehouse: "Fridge" }]);
    expect(p.semen_item).toBe("STRAW-1");
    expect(p.diagnosis).toEqual({ diagnosis_date: "2026-03-01" });
    expect(retroPayload(f, { ...check, allow_diagnosis: false }).diagnosis).toBeNull();
    expect(retroPayload({ ...f, straw: "" }, check).items).toBeUndefined();
  });
});
