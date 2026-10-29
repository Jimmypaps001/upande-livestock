import { describe, expect, it } from "vitest";
import { countsText, formatChange, formatLiveWeight, varianceNote, type ShoatEvent } from "@/lib/shoats";

const labels = { females: "Ewes", males: "Rams", young: "Lambs", others: "Others" } as const;

describe("shoat helpers", () => {
  it("says no sample rather than 0 kg", () => {
    expect(formatLiveWeight({ live_weight_kg: 0, weight_basis: "none" })).toBe("No sample");
    expect(formatLiveWeight({ live_weight_kg: 4983.04, weight_basis: "herd sample" })).toBe("4,983 kg");
  });

  it("signs the ledger change", () => {
    expect(formatChange(30)).toBe("+30");
    expect(formatChange(-3)).toBe("−3");
    expect(formatChange(0)).toBe("0");
  });

  it("names a head count's variance in the farm's words, or none", () => {
    const base = { variance: { females: -2, males: 0, young: 1, others: 0 } };
    expect(varianceNote(base, labels)).toBe("−2 ewes, +1 lambs");
    expect(varianceNote({ variance: { females: 0, males: 0, young: 0, others: 0 } }, labels)).toBeNull();
    expect(varianceNote({ variance: null }, labels)).toBeNull();
  });

  it("lists an event's counts with the born dead", () => {
    const ev = { females: 0, males: 0, young: 22, others: 0, born_dead: 2, event_type: "Birth" } as Pick<
      ShoatEvent, "females" | "males" | "young" | "others" | "born_dead" | "event_type">;
    expect(countsText(ev, labels)).toBe("22 lambs, 2 born dead");
    expect(countsText({ ...ev, young: 0, born_dead: 0 }, labels)).toBe("—");
  });
});
