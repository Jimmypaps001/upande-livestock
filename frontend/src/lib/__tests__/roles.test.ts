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

describe("an event the farm switched off", () => {
  const manager = ["Livestock Manager"];

  it("closes the page that records it, and only that page", async () => {
    const { viewOpen: open } = await import("@/lib/roles");
    const off = ["Pregnancy Diagnosis"];
    expect(open("diagnosis", manager, true, off)).toBe(false);
    expect(open("service", manager, true, off)).toBe(true);
    expect(open("calving", manager, true, off)).toBe(true);
    expect(open("diagnosis", manager, true, [])).toBe(true);
  });

  it("keeps a page of several events while any of them is on", async () => {
    const { viewOpen: open } = await import("@/lib/roles");
    expect(open("husbandry", manager, true, ["Vaccination", "Deworming"])).toBe(true);
    expect(open("husbandry", manager, true, ["Vaccination", "Deworming", "Dehorning", "Hoof Trimming"])).toBe(false);
  });

  it("never closes a page that records no event type of its own", async () => {
    const { viewOpen: open } = await import("@/lib/roles");
    const everything = ["Movement", "Calving", "Feeding", "Weight Recording", "Pregnancy Diagnosis"];
    for (const view of ["feeding", "animals", "settings", "dashboard"] as const) {
      expect(open(view, manager, true, everything)).toBe(true);
    }
  });

  it("reads the switched-off list from the page's bootstrap", async () => {
    const { eventEnabled, viewEventsOn } = await import("@/lib/roles");
    window.LIVESTOCK = { bootstrap: { disabled_events: ["Heat Detection"] } };
    try {
      expect(eventEnabled("Heat Detection")).toBe(false);
      expect(viewEventsOn("heat")).toBe(false);
      expect(viewEventsOn("service")).toBe(true);
    } finally {
      delete window.LIVESTOCK;
    }
  });
});
