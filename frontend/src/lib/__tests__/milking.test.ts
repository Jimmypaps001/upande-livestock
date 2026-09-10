import { describe, expect, it } from "vitest";
import {
  buildPayload,
  emptyForm,
  formNet,
  formRevenue,
  formatTime,
  validateForm,
  type MilkingForm,
} from "@/lib/milking";

function form(over: Partial<MilkingForm> = {}): MilkingForm {
  return { ...emptyForm(), herd: "LACTATION GROUP 2", milkingTime: "06:00", ...over };
}

describe("buildPayload", () => {
  /**
   * The whole point of this test. `create_milk_recording` reads
   * `total_yield_kg`; a payload that says `quantity` is silently a zero-yield
   * recording, and the server refuses it with a message about the yield being
   * zero rather than about the key being wrong. That mistake has been made on
   * this project once already.
   */
  it("names the yield total_yield_kg, and the day recording_date", () => {
    const p = buildPayload(form({ totalYieldKg: "412.5" }), "2026-09-01");
    expect(p.total_yield_kg).toBe(412.5);
    expect(p.recording_date).toBe("2026-09-01");
    expect(p.milking_time).toBe("06:00");
    expect(p.herd).toBe("LACTATION GROUP 2");
    expect(Object.keys(p)).not.toContain("quantity");
    expect(Object.keys(p)).not.toContain("date");
  });

  it("carries the company and operator the options call handed back", () => {
    const p = buildPayload(form({ totalYieldKg: "10" }), "2026-09-01", {
      company: "Karen Roses",
      operator: "HR-EMP-0001",
    });
    expect(p.company).toBe("Karen Roses");
    expect(p.operator).toBe("HR-EMP-0001");
  });

  it("omits the empty optionals rather than posting zeroes", () => {
    const p = buildPayload(form({ totalYieldKg: "10" }), "2026-09-01");
    expect(p).not.toHaveProperty("protein_percent");
    expect(p).not.toHaveProperty("bulk_scc");
    expect(p).not.toHaveProperty("remarks");
    expect(p).not.toHaveProperty("discard_reason");
    // These two are always sent: the server reads them with flt() and a
    // recording with nothing discarded is a real statement, not an omission.
    expect(p.discarded_kg).toBe(0);
    expect(p.price_per_kg).toBe(0);
  });

  it("sends a discard reason only once milk was actually discarded", () => {
    const withReason = buildPayload(
      form({ totalYieldKg: "10", discardedKg: "2", discardReason: "Mastitis" }),
      "2026-09-01",
    );
    expect(withReason.discard_reason).toBe("Mastitis");
    const noDiscard = buildPayload(
      form({ totalYieldKg: "10", discardedKg: "0", discardReason: "Mastitis" }),
      "2026-09-01",
    );
    expect(noDiscard).not.toHaveProperty("discard_reason");
  });

  it("rounds the head count — cows_milked is an Int on the doctype", () => {
    expect(buildPayload(form({ totalYieldKg: "10", cowsMilked: "20.6" }), "d").cows_milked).toBe(21);
    expect(buildPayload(form({ totalYieldKg: "10", cowsMilked: "" }), "d").cows_milked).toBe(0);
  });
});

describe("validateForm", () => {
  it("passes a plain, complete milking", () => {
    expect(validateForm(form({ totalYieldKg: "400", cowsMilked: "20" }))).toBeNull();
  });

  it("refuses no herd, no time and a zero yield", () => {
    expect(validateForm(form({ herd: "" }))).toMatch(/herd/i);
    expect(validateForm(form({ milkingTime: "", totalYieldKg: "1" }))).toMatch(/time/i);
    expect(validateForm(form({ totalYieldKg: "0" }))).toMatch(/greater than zero/i);
  });

  it("refuses discarding more than was milked", () => {
    expect(
      validateForm(form({ totalYieldKg: "10", discardedKg: "12", discardReason: "Spilled" })),
    ).toMatch(/cannot exceed/i);
  });

  it("mirrors the doctype: a discard needs a reason, and Other needs a note", () => {
    expect(validateForm(form({ totalYieldKg: "10", discardedKg: "2" }))).toMatch(/why/i);
    expect(
      validateForm(form({ totalYieldKg: "10", discardedKg: "2", discardReason: "Other" })),
    ).toMatch(/Describe/i);
  });
});

describe("net and revenue", () => {
  it("nets the discard off the total and prices what is left", () => {
    const f = form({ totalYieldKg: "1000", discardedKg: "60", pricePerKg: "55" });
    expect(formNet(f)).toBe(940);
    expect(formRevenue(f)).toBe(940 * 55);
  });

  it("shows a negative net rather than hiding it — the server refuses one", () => {
    expect(formNet(form({ totalYieldKg: "5", discardedKg: "9" }))).toBe(-4);
  });
});

describe("formatTime", () => {
  it("pads the hour MariaDB does not", () => {
    // Observed verbatim from frappe.client.get_list on kaitet.local.
    expect(formatTime("9:40:00")).toBe("09:40");
    expect(formatTime("13:14:00")).toBe("13:14");
  });

  it("has something to show for a row with no time", () => {
    expect(formatTime(null)).toBe("—");
    expect(formatTime("")).toBe("—");
  });
});
