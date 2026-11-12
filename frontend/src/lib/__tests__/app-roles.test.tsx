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

function open(roles: string[], hash: string) {
  window.LIVESTOCK = { bootstrap: { user: "u@x.com", full_name: "U", roles } };
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
