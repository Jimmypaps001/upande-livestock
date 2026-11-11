import { describe, expect, it } from "vitest";

import {
  canMix,
  concentratesInUse,
  landingView,
  NUTRITIONIST_ROLE,
  NUTRITIONIST_VIEWS,
  nutritionistOnly,
  viewAllowed,
  viewOpen,
} from "@/lib/roles";

describe("the nutritionist role in the web app", () => {
  const only = [NUTRITIONIST_ROLE, "All", "Guest"];

  it("is nutritionist-only when no wider farm role is held", () => {
    expect(nutritionistOnly(only)).toBe(true);
    expect(nutritionistOnly([NUTRITIONIST_ROLE, "Livestock Manager"])).toBe(false);
    expect(nutritionistOnly(["Livestock Stores"])).toBe(false);
    expect(nutritionistOnly([NUTRITIONIST_ROLE, "Administrator"])).toBe(false);
  });

  it("sees the feed screens and nothing else", () => {
    for (const v of ["ration-editor", "rations", "concentrate", "stock"] as const) {
      expect(viewAllowed(v, only)).toBe(true);
    }
    for (const v of ["dashboard", "animals", "feeding", "procurement", "settings"] as const) {
      expect(viewAllowed(v, only)).toBe(false);
    }
    expect(viewAllowed("animals", ["Livestock Attendant"])).toBe(true);
  });

  it("lands on the Ration Editor", () => {
    expect(NUTRITIONIST_VIEWS[0]).toBe("ration-editor");
    expect(landingView(only)).toBe("ration-editor");
    expect(landingView(["Livestock Stores"])).toBe("feeding");
  });

  it("does not mix", () => {
    expect(canMix(only)).toBe(false);
    expect(canMix(["Livestock Stores"])).toBe(true);
  });
});

describe("the Concentrate window", () => {
  it("opens only where concentrate is in use", () => {
    expect(concentratesInUse(true)).toBe(true);
    expect(concentratesInUse(false)).toBe(false);
    expect(viewOpen("concentrate", ["Livestock Manager"], true)).toBe(true);
    expect(viewOpen("concentrate", ["Livestock Manager"], false)).toBe(false);
    // Nothing else depends on it.
    expect(viewOpen("ration-editor", ["Livestock Manager"], false)).toBe(true);
    expect(viewOpen("feeding", ["Livestock Manager"], false)).toBe(true);
  });

  it("still follows the role rule where it is in use", () => {
    const only = [NUTRITIONIST_ROLE];
    expect(viewOpen("concentrate", only, true)).toBe(true);
    expect(viewOpen("concentrate", only, false)).toBe(false);
    expect(viewOpen("feeding", only, true)).toBe(false);
  });
});
