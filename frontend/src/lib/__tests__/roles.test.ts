import { describe, expect, it } from "vitest";

import {
  limitedViews,
  landingView,
  QUALITY_ROLE,
  QUALITY_VIEWS,
  qualityOnly,
  viewAllowed,
} from "@/lib/roles";
import { VIEWS } from "@/lib/router";

describe("the Livestock Quality role in the web app", () => {
  const only = [QUALITY_ROLE, "All", "Guest"];

  it("is quality-only when no wider farm role is held", () => {
    expect(qualityOnly(only)).toBe(true);
    expect(qualityOnly([QUALITY_ROLE, "Livestock Manager"])).toBe(false);
    expect(qualityOnly([QUALITY_ROLE, "Livestock Milker"])).toBe(false);
    expect(qualityOnly([QUALITY_ROLE, "Livestock Stores"])).toBe(false);
    expect(qualityOnly([QUALITY_ROLE, "System Manager"])).toBe(false);
    expect(qualityOnly([QUALITY_ROLE, "Administrator"])).toBe(false);
    expect(qualityOnly(["Livestock Attendant"])).toBe(false);
    expect(qualityOnly([])).toBe(false);
  });

  it("sees the quality screens and nothing else", () => {
    for (const v of ["quality", "feed-quality"] as const) {
      expect(viewAllowed(v, only)).toBe(true);
    }
    const others = VIEWS.filter((v) => !QUALITY_VIEWS.includes(v));
    expect(others.length).toBeGreaterThan(20);
    for (const v of others) expect(viewAllowed(v, only)).toBe(false);
  });

  it("lands on Quality", () => {
    expect(QUALITY_VIEWS[0]).toBe("quality");
    expect(landingView(only)).toBe("quality");
  });

  it("changes nothing for anyone who also holds a wider farm role", () => {
    for (const roles of [
      [QUALITY_ROLE, "Livestock Manager"],
      ["Livestock Attendant"],
      ["System Manager"],
      [],
    ]) {
      for (const v of VIEWS) expect(viewAllowed(v, roles)).toBe(true);
    }
    expect(landingView(["Livestock Manager", QUALITY_ROLE])).toBe("feeding");
    expect(landingView([])).toBe("feeding");
  });

  it("reads the roles from the page's bootstrap by default", () => {
    window.LIVESTOCK = { bootstrap: { roles: [QUALITY_ROLE] } };
    try {
      expect(qualityOnly()).toBe(true);
      expect(viewAllowed("feeding")).toBe(false);
      expect(viewAllowed("quality")).toBe(true);
    } finally {
      delete window.LIVESTOCK;
    }
  });
});

describe("limitedViews", () => {
  it("is null for an unrestricted user and the role's screens for a restricted one", () => {
    expect(limitedViews(["Livestock Manager"])).toBeNull();
    expect(limitedViews([QUALITY_ROLE])).toEqual(["quality", "feed-quality"]);
  });
});
