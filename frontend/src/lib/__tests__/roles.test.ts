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

describe("an event the farm switched off", () => {
  const manager = ["Livestock Manager"];

  it("closes the page that records it, and only that page", async () => {
    const { viewOpen: open } = await import("@/lib/roles");
    const off = ["Pregnancy Diagnosis"];
    expect(open("diagnosis", manager, off)).toBe(false);
    expect(open("service", manager, off)).toBe(true);
    expect(open("calving", manager, off)).toBe(true);
    expect(open("diagnosis", manager, [])).toBe(true);
    expect(open("drying-off", manager, ["Drying Off"])).toBe(false);
  });

  it("keeps a page of several events while any of them is on", async () => {
    const { viewOpen: open } = await import("@/lib/roles");
    expect(open("husbandry", manager, ["Vaccination", "Deworming"])).toBe(true);
    expect(open("husbandry", manager, ["Vaccination", "Deworming", "Dehorning", "Hoof Trimming"])).toBe(false);
  });

  it("never closes a page that records no event type of its own", async () => {
    const { viewOpen: open } = await import("@/lib/roles");
    const everything = ["Movement", "Calving", "Feeding", "Weight Recording", "Pregnancy Diagnosis"];
    for (const view of ["ration-editor", "rations", "concentrate", "animals", "settings", "dashboard", "transactions"] as const) {
      expect(open(view, manager, everything)).toBe(true);
    }
  });

  it("closes Feeding, which issues feed, but keeps the Ration Editor that only designs it", async () => {
    const { viewOpen: open } = await import("@/lib/roles");
    expect(open("feeding", manager, ["Feeding"])).toBe(false);
    expect(open("ration-editor", manager, ["Feeding"])).toBe(true);
    expect(open("rations", manager, ["Feeding"])).toBe(true);
    expect(open("feeding", manager, [])).toBe(true);
  });

  it("lands on the Dashboard, not on a switched-off Feeding that would send you on again", async () => {
    const { landingView: landing, viewOpen: open } = await import("@/lib/roles");
    expect(landing(manager, [])).toBe("feeding");
    expect(landing(manager, ["Feeding"])).toBe("dashboard");
    expect(open(landing(manager, ["Feeding"]), manager, ["Feeding"])).toBe(true);
  });

  it("combines with the role limit instead of replacing it", async () => {
    const { landingView: landing, viewOpen: open } = await import("@/lib/roles");
    const lab = [QUALITY_ROLE];
    // The lab still lands on Quality, switched-off Feeding or not.
    expect(landing(lab, ["Feeding"])).toBe("quality");
    // Its own screens open; everything else stays shut for a role reason.
    expect(open("quality", lab, ["Feeding"])).toBe(true);
    expect(open("animals", lab, [])).toBe(false);
    // A switched-off event shuts its page even for a role that could open it.
    expect(open("diagnosis", manager, ["Pregnancy Diagnosis"])).toBe(false);
  });

  it("reads the switched-off list from the page's bootstrap", async () => {
    const { eventEnabled, viewEventsOn, viewOpen: open } = await import("@/lib/roles");
    window.LIVESTOCK = { bootstrap: { disabled_events: ["Heat Detection"] } };
    try {
      expect(eventEnabled("Heat Detection")).toBe(false);
      expect(viewEventsOn("heat")).toBe(false);
      expect(viewEventsOn("service")).toBe(true);
      expect(open("heat", manager)).toBe(false);
    } finally {
      delete window.LIVESTOCK;
    }
  });
});
