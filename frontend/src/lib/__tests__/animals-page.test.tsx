import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The Animals page, on the server's data.
 *
 * It was a layout over `animals-sample.ts` — a demo with made-up figures on the
 * most-looked-at page in the app. What is pinned here is that the page asks the
 * server and draws what comes back, and that nothing on it is invented: a
 * heifer who has never been served has no conception rate, and the page must
 * not fill that gap with a zero.
 */

const list = {
  ok: true,
  animals: [
    { id: "A057/22", name: "APIJA", sex: "Female", herd: "Lactation Group 3 TEST HERD",
      breed: "Ayrshire", bornOn: "2022-03-04", status: "Active", stage: "open", photo: null },
    { id: "A085/22", name: "ATLAS", sex: "Female", herd: "STEAMERS",
      breed: null, bornOn: "2022-12-07", status: "Active", stage: "open", photo: null },
  ],
};

const profile = {
  ok: true,
  ...list.animals[0],
  stage: "confirmed",
  dam: null,
  sire: null,
  lastCalving: null,
  expectedCalving: null,
  cycle: { stage: "confirmed", dayInStage: 206, daysInMilk: null,
           nextUp: "Drying off, then calving", nextOn: null },
  kpis: { parity: 0, services: 1, conceptions: 1, abortions: 0, conceptionRate: 100,
          calvingInterval: null, lactationYield: null, yieldIndex: null, treatments: 0 },
  milestones: [
    { kind: "service", on: "2025-10-13", label: "Served", detail: "A.I." },
    { kind: "confirmed", on: "2026-02-20", label: "Checked", detail: "Confirmed" },
  ],
  spells: [{ herd: "Lactation Group 3 TEST HERD", from: "2022-03-04", to: null, unrecorded: false }],
};

const call = vi.fn(async (method?: string): Promise<Record<string, unknown>> => {
  const m = method || "";
  if (m.includes("animal_profile")) return profile;
  if (m.includes("animal_list")) return list;
  if (m.includes("herd_benchmarks")) return { ok: true, cows: 2, parity: 1, conception_rate: 60 };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Animals } = await import("@/pages/Animals");

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
      <Animals />
    </ToastProvider>
    </TooltipProvider>,
  );

describe("the Animals page", () => {
  beforeEach(() => call.mockClear());

  it("asks the server for the herd instead of shipping one", async () => {
    draw();
    await waitFor(() =>
      expect(call.mock.calls.some((c) => String(c[0]).includes("animal_list"))).toBe(true),
    );
    await waitFor(() => expect(screen.getAllByText(/APIJA/).length).toBeGreaterThan(0));
  });

  it("fetches the profile of whoever is selected", async () => {
    draw();
    await waitFor(() =>
      expect(call.mock.calls.some((c) => String(c[0]).includes("animal_profile"))).toBe(true),
    );
  });

  it("draws her real milestones", async () => {
    draw();
    await waitFor(() => expect(screen.getAllByText(/Served/).length).toBeGreaterThan(0));
  });

  it("no longer claims to be a layout rather than a record", async () => {
    draw();
    await waitFor(() => expect(screen.getAllByText(/APIJA/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/The animals, dates and figures below are/)).toBeNull();
  });

  it("draws her record the moment she is picked, not when her figures land", async () => {
    // The page used to gate the whole record on the profile, so choosing a cow
    // blanked everything until the second request came back. Each section
    // stands in for itself instead.
    let release: (v: unknown) => void = () => {};
    call.mockImplementation(async (method?: string) => {
      const m = method || "";
      if (m.includes("animal_profile")) {
        await new Promise((r) => { release = r; });
        return profile;
      }
      if (m.includes("animal_list")) return list;
      return { ok: true };
    });
    draw();
    // Her name and her age are on the list row, so they are there at once —
    // and the sections she is waiting on are drawn as their own shapes.
    await waitFor(() => expect(screen.getByText("Where she is in the cycle")).toBeTruthy());
    expect(screen.getByText("Her life so far")).toBeTruthy();
    expect(screen.getByText("Everything recorded")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /Compare against the herd/ }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    // Release only once the request has actually been made: `release` is
    // captured inside the promise the profile call creates, so resolving before
    // the call is made resolves nothing and the test hangs on a page that is
    // behaving perfectly.
    await waitFor(() =>
      expect(call.mock.calls.some((c) => String(c[0]).includes("animal_profile"))).toBe(true),
    );
    release(null);
    await waitFor(() => expect(screen.getAllByText(/Served/).length).toBeGreaterThan(0));
  });

  it("says so when the herd cannot be loaded", async () => {
    call.mockImplementationOnce(async () => ({ error: "You are not permitted to read Animal." }));
    draw();
    await waitFor(() =>
      expect(screen.getByText(/not permitted to read Animal/)).toBeTruthy(),
    );
  });
});
