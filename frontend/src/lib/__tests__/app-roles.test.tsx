import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/use-notifications", () => ({
  useUnreadNotifications: () => ({ unread: 0, refresh: async () => {}, setUnread: () => {} }),
}));
// Pages are not under test; each stands in as its own name.
vi.mock("@/pages/Quality", () => ({ Quality: () => <div>QUALITY PAGE</div> }));
vi.mock("@/pages/FeedQuality", () => ({ FeedQuality: () => <div>FEEDQ PAGE</div> }));
vi.mock("@/pages/Feeding", () => ({ Feeding: () => <div>FEEDING PAGE</div> }));
vi.mock("@/pages/Animals", () => ({ Animals: () => <div>ANIMALS PAGE</div> }));
vi.mock("@/pages/Dashboard", () => ({ Dashboard: () => <div>DASHBOARD PAGE</div> }));
vi.mock("@/pages/Breeding", () => ({
  Service: () => <div>SERVICE PAGE</div>,
  Diagnosis: () => <div>DIAGNOSIS PAGE</div>,
  Abortion: () => <div>ABORTION PAGE</div>,
  DryingOff: () => <div>DRYING PAGE</div>,
  Heat: () => <div>HEAT PAGE</div>,
}));

import { App } from "@/App";

beforeAll(() => {
  window.matchMedia = ((q: string) => ({
    matches: false, media: q, onchange: null, addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
});

afterEach(() => {
  cleanup();
  delete window.LIVESTOCK;
  window.location.hash = "";
});

function open(roles: string[], hash: string, disabled_events: string[] = []) {
  window.LIVESTOCK = { bootstrap: { user: "u@x.com", full_name: "U", roles, disabled_events } };
  window.location.hash = hash;
  return render(<App />);
}

describe("routes for a Livestock Quality-only user", { timeout: 30_000 }, () => {
  it("sends a direct URL to another screen to Quality, rendering nothing of it", async () => {
    open(["Livestock Quality"], "#/animals");
    expect(await screen.findByText("QUALITY PAGE")).toBeTruthy();
    expect(screen.queryByText("ANIMALS PAGE")).toBeNull();
    expect(window.location.hash).toBe("#/quality");
  });

  it("lands an empty hash (Feeding by default) on Quality", async () => {
    open(["Livestock Quality"], "");
    expect(await screen.findByText("QUALITY PAGE")).toBeTruthy();
    expect(screen.queryByText("FEEDING PAGE")).toBeNull();
  });

  it("opens Feed vs quality directly", async () => {
    open(["Livestock Quality"], "#/feed-quality");
    expect(await screen.findByText("FEEDQ PAGE")).toBeTruthy();
    expect(window.location.hash).toBe("#/feed-quality");
  });

  it("leaves a user with a wider role where they asked to be", async () => {
    open(["Livestock Quality", "Livestock Manager"], "#/animals");
    expect(await screen.findByText("ANIMALS PAGE")).toBeTruthy();
    expect(window.location.hash).toBe("#/animals");
  });
});

describe("routes when the farm switched an event off", { timeout: 30_000 }, () => {
  const manager = ["Livestock Manager"];

  it("sends the page of a switched-off event to the landing screen and hides it from the sidebar", async () => {
    open(manager, "#/diagnosis", ["Pregnancy Diagnosis"]);
    expect(await screen.findByText("FEEDING PAGE")).toBeTruthy();
    expect(screen.queryByText("DIAGNOSIS PAGE")).toBeNull();
    expect(window.location.hash).toBe("#/feeding");
    expect(screen.queryByText("Pregnancy Diagnosis")).toBeNull();
    // Its neighbours are still on the menu.
    expect(screen.getAllByText("Service").length).toBeGreaterThan(0);
  });

  it("opens the same page when the event is on", async () => {
    open(manager, "#/diagnosis", []);
    expect(await screen.findByText("DIAGNOSIS PAGE")).toBeTruthy();
  });

  it("lands on the Dashboard, once, when Feeding itself is switched off", async () => {
    open(manager, "#/feeding", ["Feeding"]);
    expect(await screen.findByText("DASHBOARD PAGE")).toBeTruthy();
    expect(window.location.hash).toBe("#/dashboard");
  });

  it("keeps the role limit and the switch together", async () => {
    open(["Livestock Quality"], "#/service", ["Service"]);
    expect(await screen.findByText("QUALITY PAGE")).toBeTruthy();
    expect(window.location.hash).toBe("#/quality");
  });
});
