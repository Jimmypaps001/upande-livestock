import { describe, expect, it } from "vitest";

import { canMix, NUTRITIONIST_ROLE, nutritionistOnly, viewAllowed } from "@/lib/roles";

describe("the nutritionist role in the web app", () => {
  const only = [NUTRITIONIST_ROLE, "All", "Guest"];

  it("is nutritionist-only when no wider farm role is held", () => {
    expect(nutritionistOnly(only)).toBe(true);
    expect(nutritionistOnly([NUTRITIONIST_ROLE, "Livestock Manager"])).toBe(false);
    expect(nutritionistOnly(["Livestock Stores"])).toBe(false);
    expect(nutritionistOnly([NUTRITIONIST_ROLE, "Administrator"])).toBe(false);
  });

  it("sees the feed screens and nothing else", () => {
    for (const v of ["feed-design", "ration-editor", "rations", "concentrate", "stock"] as const) {
      expect(viewAllowed(v, only)).toBe(true);
    }
    for (const v of ["dashboard", "animals", "feeding", "procurement", "settings"] as const) {
      expect(viewAllowed(v, only)).toBe(false);
    }
    expect(viewAllowed("animals", ["Livestock Attendant"])).toBe(true);
  });

  it("does not mix", () => {
    expect(canMix(only)).toBe(false);
    expect(canMix(["Livestock Stores"])).toBe(true);
  });
});
