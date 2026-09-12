import { describe, expect, it } from "vitest";
import { DOCK_LINE, RAMP } from "@/lib/use-dock-progress";

/**
 * The geometry the title's flight depends on.
 *
 * The flight itself is a transform between two measured slots and cannot be
 * asserted without a laid-out page — it is checked in the browser instead. What
 * IS worth pinning here is the pair of constants that decide when the flight
 * happens, because a dock line at zero would put the pill under the window
 * edge and a ramp of a thousand would mean it never triggers.
 */
describe("where the title hands over", () => {
  it("rests the pill clear of the top edge", () => {
    expect(DOCK_LINE).toBeGreaterThan(24);
    expect(DOCK_LINE).toBeLessThan(160);
  });

  it("triggers within a short scroll, so it reads as one movement", () => {
    expect(RAMP).toBeGreaterThan(32);
    expect(RAMP).toBeLessThan(160);
  });
});
