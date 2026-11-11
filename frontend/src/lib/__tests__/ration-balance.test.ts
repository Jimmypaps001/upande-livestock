import { describe, expect, it } from "vitest";
import {
  changeTotal,
  editLine,
  hasDefiniteTotal,
  kgTotal,
  rebalance,
  rowKilos,
  sharesOf,
  toggleLock,
  type BalanceRow,
} from "@/lib/ration-maths";

/**
 * Kilos and % of intake, both editable, with locks: the farm's rule.
 *
 * "If I edit row 1 I lock it, edit row 2 lock, row 3 lock and moving onwards;
 * the lock should be on the value being edited, and the lock should only apply
 * if we have a definite kg; for percentages the lock is always there."
 */

type Row = BalanceRow & { item: string };
const kg = (item: string, qty: string): Row => ({ item, qty, unit: "kg" });

const qtys = (rows: Row[]) => rows.map((r) => r.qty);
const pcts = (rows: Row[]) => rows.map((r) => r.pct);
const locks = (rows: Row[]) => rows.map((r) => !!r.locked);
const pctSum = (rows: Row[]) => rows.reduce((s, r) => s + (parseFloat(r.pct || "0") || 0), 0);

/** 7 + 4 + 3 kg held to a definite 14 kg a head. */
function fourteen() {
  return changeTotal([kg("silage", "7"), kg("germ", "4"), kg("hay", "3")], "", "14");
}

describe("shares of intake", () => {
  it("add up to exactly 100, the last line taking up the rounding", () => {
    expect(sharesOf([kg("a", "1"), kg("b", "1"), kg("c", "1")])).toEqual(["33.33", "33.33", "33.34"]);
  });

  it("leave doses and empty lines out", () => {
    expect(sharesOf([kg("a", "3"), { qty: "7", unit: "Gram" }, kg("b", "")])).toEqual(["100", "", ""]);
  });

  it("a total is definite only once a positive figure is typed", () => {
    expect(hasDefiniteTotal("")).toBe(false);
    expect(hasDefiniteTotal("0")).toBe(false);
    expect(hasDefiniteTotal("14")).toBe(true);
  });
});

describe("with no definite total", () => {
  const rows = [kg("silage", "15"), kg("germ", "5")];

  it("typing a line's kilos changes that line only, re-works every share and locks nothing", () => {
    const out = editLine(rows, "", 0, "qty", "25");
    expect(out.total).toBe("");
    expect(qtys(out.rows)).toEqual(["25", "5"]);
    expect(pcts(out.rows)).toEqual(["83.33", "16.67"]);
    expect(locks(out.rows)).toEqual([false, false]);
    expect(out.notice).toBeNull();
  });

  it("typing a % makes the current sum the total, locks the line and rebalances the rest", () => {
    const out = editLine([...rows, kg("hay", "5")], "", 0, "pct", "50");
    expect(out.total).toBe("25");
    expect(qtys(out.rows)).toEqual(["12.5", "6.25", "6.25"]);
    expect(pcts(out.rows)).toEqual(["50", "25", "25"]);
    expect(locks(out.rows)).toEqual([true, false, false]);
  });

  it("a % with nothing weighed yet asks for the kilos first", () => {
    const out = editLine([kg("silage", ""), kg("germ", "")], "", 0, "pct", "60");
    expect(out.total).toBe("");
    expect(out.rows[0].pct).toBe("60");
    expect(out.rows[0].locked).toBeFalsy();
    expect(out.notice).toMatch(/kilos per head first/);
  });
});

describe("with a definite total", () => {
  it("typing a line's kilos locks it and rescales the unlocked lines in proportion", () => {
    const out = editLine(fourteen().rows, "14", 0, "qty", "8");
    expect(qtys(out.rows)).toEqual(["8", "3.429", "2.571"]);
    expect(pcts(out.rows)).toEqual(["57.14", "24.49", "18.37"]);
    expect(locks(out.rows)).toEqual([true, false, false]);
    expect(kgTotal(out.rows)).toBeCloseTo(14, 9);
    expect(pctSum(out.rows)).toBeCloseTo(100, 9);
    expect(out.notice).toBeNull();
  });

  it("the next line typed locks too, and the first keeps its figure", () => {
    const one = editLine(fourteen().rows, "14", 0, "qty", "8");
    const two = editLine(one.rows, "14", 1, "pct", "25");
    expect(qtys(two.rows)).toEqual(["8", "3.5", "2.5"]);
    expect(pcts(two.rows)).toEqual(["57.14", "25", "17.86"]);
    expect(locks(two.rows)).toEqual([true, true, false]);
  });

  it("keeps a figure as it is being typed", () => {
    const out = editLine(fourteen().rows, "14", 0, "qty", "8.");
    expect(out.rows[0].qty).toBe("8.");
    const pct = editLine(fourteen().rows, "14", 0, "pct", "50.");
    expect(pct.rows[0].pct).toBe("50.");
  });

  it("the last unlocked line cannot move: it takes what is left and says so", () => {
    let s = editLine(fourteen().rows, "14", 0, "qty", "8").rows;
    s = editLine(s, "14", 1, "qty", "3.5").rows;
    const out = editLine(s, "14", 2, "qty", "1");
    expect(qtys(out.rows)).toEqual(["8", "3.5", "2.5"]);
    expect(out.notice).toMatch(/Every other row is locked, so this one takes the remaining 2.5 kg/);
    expect(kgTotal(out.rows)).toBeCloseTo(14, 9);
  });

  it("clamps a line to what the locked lines leave, and says how much they use", () => {
    let s = editLine(fourteen().rows, "14", 0, "qty", "8").rows;
    s = editLine(s, "14", 1, "qty", "5.2").rows;
    const out = editLine(s, "14", 2, "qty", "5");
    expect(out.rows[2].qty).toBe("0.8");
    expect(out.notice).toBe("Locked rows already use 13.2 of 14 kg — unlock a row to give it more.");
    expect(kgTotal(out.rows)).toBeCloseTo(14, 9);
  });

  it("clamps a % the same way", () => {
    const s = editLine(fourteen().rows, "14", 0, "pct", "90").rows;
    const out = editLine(s, "14", 1, "pct", "20");
    expect(out.rows[1].pct).toBe("10");
    expect(out.rows[1].qty).toBe("1.4");
    expect(out.rows[2].qty).toBe("");
    expect(out.notice).toMatch(/Locked rows already use 12.6 of 14 kg/);
  });

  it("no line may take more than the whole total", () => {
    const out = editLine(fourteen().rows, "14", 0, "qty", "20");
    expect(qtys(out.rows)).toEqual(["14", "", ""]);
    expect(out.notice).toBe("A row cannot take more than the whole 14 kg.");
  });

  it("unlocked lines with nothing in them share the rest evenly", () => {
    const rows = changeTotal([kg("a", "10"), kg("b", ""), kg("c", "")], "", "10").rows;
    const out = editLine(rows, "10", 0, "qty", "4");
    expect(qtys(out.rows)).toEqual(["4", "3", "3"]);
    expect(pcts(out.rows)).toEqual(["40", "30", "30"]);
  });

  it("leaves doses alone: per head, outside the 100%, never locked", () => {
    const rows = changeTotal([kg("silage", "15"), kg("germ", "5"), { item: "dv", qty: "7", unit: "Gram" }], "", "20").rows;
    const out = editLine(rows, "20", 2, "qty", "9");
    expect(qtys(out.rows)).toEqual(["15", "5", "9"]);
    expect(out.rows[2].locked).toBeFalsy();
    const moved = editLine(rows, "20", 0, "qty", "10");
    expect(moved.rows[2].qty).toBe("7");
    expect(toggleLock(rows, 2, "20")).toBe(rows);
  });

  it("balances a line in a store unit by its kilos and writes it back in its unit", () => {
    const rows = changeTotal(
      [kg("silage", "15"), { item: "molasses", qty: "3", unit: "Litre", kgPer: 1.4 }],
      "",
      "19.2",
    ).rows;
    const out = editLine(rows, "19.2", 0, "qty", "12.2");
    // 7 kg of molasses at 1.4 kg a litre.
    expect(out.rows[1].qty).toBe("5");
    expect(rowKilos(out.rows[1])).toBeCloseTo(7, 9);
  });
});

describe("changing the total", () => {
  it("keeps every line's %, locked lines included, and their kilos follow (57.14% of 28 is 15.999)", () => {
    const s = editLine(fourteen().rows, "14", 0, "qty", "8").rows;
    const out = changeTotal(s, "14", "28");
    expect(qtys(out.rows)).toEqual(["15.999", "6.857", "5.144"]);
    expect(pcts(out.rows)).toEqual(pcts(s));
    expect(locks(out.rows)).toEqual([true, false, false]);
    expect(kgTotal(out.rows)).toBeCloseTo(28, 9);
  });

  it("does not drift as the figure is typed a keystroke at a time", () => {
    const s = editLine(fourteen().rows, "14", 1, "pct", "33.33").rows;
    const a = changeTotal(s, "14", "1");
    const b = changeTotal(a.rows, "1", "14");
    expect(pcts(b.rows)).toEqual(pcts(s));
    expect(kgTotal(b.rows)).toBeCloseTo(14, 9);
  });

  it("typed for the first time, it scales the recipe as it stands", () => {
    const out = changeTotal([kg("silage", "15"), kg("germ", "5")], "", "24");
    expect(qtys(out.rows)).toEqual(["18", "6"]);
    expect(pcts(out.rows)).toEqual(["75", "25"]);
  });

  it("cleared, every lock goes and the lines keep their kilos", () => {
    const s = editLine(fourteen().rows, "14", 0, "qty", "8").rows;
    const out = changeTotal(s, "14", "");
    expect(locks(out.rows)).toEqual([false, false, false]);
    expect(qtys(out.rows)).toEqual(qtys(s));
  });

  it("says so when the shares do not come to 100", () => {
    const rows: Row[] = [
      { ...kg("a", "5"), pct: "50", locked: true },
      { ...kg("b", "4"), pct: "40", locked: true },
    ];
    expect(changeTotal(rows, "10", "20").notice).toMatch(/90%, not 100%/);
  });
});

describe("adding and taking out lines", () => {
  it("a new line starts at nothing, unlocked, and moves nobody", () => {
    const s = editLine(fourteen().rows, "14", 0, "qty", "8").rows;
    const out = rebalance([...s, kg("bran", "")], "14");
    expect(qtys(out.rows)).toEqual([...qtys(s), ""]);
    expect(out.rows[3].locked).toBeFalsy();
  });

  it("a line taken out hands its share to the unlocked lines", () => {
    const s = editLine(fourteen().rows, "14", 0, "qty", "8").rows;
    const out = rebalance([s[0], s[2]], "14");
    expect(qtys(out.rows)).toEqual(["8", "6"]);
    expect(pcts(out.rows)).toEqual(["57.14", "42.86"]);
  });

  it("with only locked lines left, says what is unallocated rather than breaking the total quietly", () => {
    let s = editLine(fourteen().rows, "14", 0, "qty", "8").rows;
    s = editLine(s, "14", 1, "qty", "3").rows;
    const out = rebalance([s[0], s[1]], "14");
    expect(out.notice).toMatch(/Every row is locked and they come to 11 of 14 kg/);
  });

  it("without a definite total, just re-works the shares", () => {
    const out = rebalance([kg("a", "3"), kg("b", "1")], "");
    expect(pcts(out.rows)).toEqual(["75", "25"]);
  });
});

describe("locking by hand", () => {
  it("only against a definite total", () => {
    const rows = [kg("a", "3"), kg("b", "1")];
    expect(toggleLock(rows, 0, "")).toBe(rows);
    expect(toggleLock(rows, 0, "4")[0].locked).toBe(true);
    expect(toggleLock(toggleLock(rows, 0, "4"), 0, "4")[0].locked).toBe(false);
  });
});

describe("whatever is typed, in whatever order", () => {
  it("the lines always come to the total and to 100%", () => {
    // A small deterministic generator, so a failure replays.
    let seed = 42;
    const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
    for (let trial = 0; trial < 300; trial++) {
      const total = String(Math.round((5 + rnd() * 40) * 10) / 10);
      let rows = changeTotal(
        Array.from({ length: 2 + Math.floor(rnd() * 5) }, (_, i) => kg(`f${i}`, String(Math.round(rnd() * 10000) / 1000))),
        "",
        total,
      ).rows;
      for (let step = 0; step < 12; step++) {
        const i = Math.floor(rnd() * rows.length);
        const roll = rnd();
        if (roll < 0.15) rows = toggleLock(rows, i, total);
        else if (roll < 0.55) rows = editLine(rows, total, i, "qty", String(Math.round(rnd() * 15000) / 1000)).rows;
        else rows = editLine(rows, total, i, "pct", String(Math.round(rnd() * 6000) / 100)).rows;
        // Locked or not, every step keeps the sums.
        expect(kgTotal(rows)).toBeCloseTo(Number(total), 6);
        expect(pctSum(rows)).toBeCloseTo(100, 6);
        expect(rows.every((r) => rowKilos(r) >= 0)).toBe(true);
      }
    }
  });
});
