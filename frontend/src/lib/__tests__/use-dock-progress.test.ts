import { describe, expect, it } from "vitest";
import { DOCK_LINE, RAMP, dockFade, headingFade } from "@/lib/use-dock-progress";

/**
 * The handover between the heading and the dock.
 *
 * The invariant worth guarding is not "it fades" — it is that the two are
 * never both on screen. A straight crossfade puts both at half opacity in the
 * middle, which reads as two titles rather than one moving, and is exactly
 * what this replaced.
 */
describe("the title handover", () => {
  it("gives the heading the title at rest", () => {
    expect(headingFade(0)).toBe(1);
    expect(dockFade(0)).toBe(0);
  });

  it("gives the dock the title once the heading has gone", () => {
    expect(headingFade(1)).toBe(0);
    expect(dockFade(1)).toBe(1);
  });

  it("never has both of them visible at once", () => {
    // Swept, not spot-checked. The ramps cross inside a tenth of the movement,
    // and a coarse sample steps straight over it — sampling the real page every
    // ten pixels across a seventy-two pixel ramp reported no overlap at all,
    // which was the sampling and not the truth.
    //
    // The bar is "not visible", not "not present". They do cross, and at the
    // crossing each is under a tenth of an opacity — two texts at 9% on a warm
    // white page, in different sizes and positions. The straight crossfade this
    // replaced peaked at 0.5, which is the one a reader actually sees.
    let worst = 0;
    for (let p = 0; p <= 1.0001; p += 0.002) {
      worst = Math.max(worst, Math.min(headingFade(p), dockFade(p)));
    }
    expect(worst).toBeLessThan(0.12);
    // And nowhere near the crossfade it replaced.
    expect(worst).toBeLessThan(0.5 / 4);
  });

  it("hands over in the middle, not at one end", () => {
    // Both gone by the midpoint is the stagger working; if either ramp drifted
    // to cover the whole range this is what would notice.
    expect(headingFade(0.5)).toBeLessThan(0.15);
    expect(dockFade(0.5)).toBeLessThan(0.15);
    expect(headingFade(0.3)).toBeGreaterThan(0.4);
    expect(dockFade(0.7)).toBeGreaterThan(0.4);
  });

  it("keeps the dock clear of the heading it replaces", () => {
    // The pill rests below the top edge, and the ramp is short enough to read
    // as one movement rather than a long dissolve.
    expect(DOCK_LINE).toBeGreaterThan(0);
    expect(RAMP).toBeGreaterThan(32);
    expect(RAMP).toBeLessThan(160);
  });
});
