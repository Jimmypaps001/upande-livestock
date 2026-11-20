import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnimalSearch } from "@/components/animals/AnimalSearch";
import { BullPanel } from "@/components/animals/BullPanel";
import { burdenMarker, money, rowLine, verdict, type BullEconomics } from "@/lib/bulls";
import type { AnimalSummary } from "@/lib/animals";

const econ = (over: Partial<BullEconomics> = {}): BullEconomics => ({
  animal: "B001/22",
  purpose: "Cull for sale at birth",
  kept_as_cost: true,
  days_kept: 40,
  feed: { cost: 6000, days_fed: 38, per_day: 157.9, method: "Herd feed cost per head per day." },
  value: { amount: 5000, source: "price_per_kg", as_of: "2026-11-20" },
  net: -1000,
  burden_since: "2026-11-01",
  growth: { kg: 50, on: "2026-11-10", adg: 0.8, birth_kg: 30, series: [{ on: "2026-10-10", kg: 30 }, { on: "2026-11-10", kg: 50 }] },
  currency: "KES",
  ...over,
});

const { call } = vi.hoisted(() => ({ call: vi.fn() }));
call.mockImplementation(async (method?: string) => {
  if (String(method).includes("bull_economics")) return { ok: true, ...econ() };
  return { ok: true };
});
vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const mk = (id: string, sex: "Female" | "Male", herd: string): AnimalSummary => ({
  id, name: id, sex, herd, breed: null, bornOn: "2026-01-01", status: "Active", stage: "open", photo: null,
});

describe("bull wording", () => {
  it("shows a loss with a minus and the burden date", () => {
    expect(money(-1000)).toBe("−KES 1,000");
    expect(money(null)).toBe("—");
    expect(burdenMarker(econ())).toBe("Burden since 2026-11-01");
    expect(burdenMarker(econ({ burden_since: null }))).toBeNull();
    expect(verdict(econ())).toEqual({ text: "Net −KES 1,000", loss: true });
  });

  it("says no value rather than inventing a zero", () => {
    const v = verdict(econ({ net: null, value: { amount: null, source: null, as_of: null } }));
    expect(v.text).toContain("no value");
    expect(v.loss).toBe(false);
  });
});

describe("the list row line", () => {
  it("says each figure once", () => {
    const t = rowLine(econ()).text;
    expect(t.match(/Feed/g)).toHaveLength(1);
    expect(t).toContain("Burden since 2026-11-01");
  });
  it("gives a bull with no value a line too", () => {
    const l = rowLine(econ({ net: null, burden_since: null, value: { amount: null, source: null, as_of: null } }));
    expect(l.text).toMatch(/^Feed .* · no value$/);
  });
});

describe("the bull panel", () => {
  beforeEach(() => call.mockClear());

  it("asks for his economics and flags every day kept as cost", async () => {
    render(<BullPanel animal="B001/22" />);
    await waitFor(() => expect(screen.getByText(/Burden since 2026-11-01/)).toBeTruthy());
    expect(screen.getByText(/every day he is kept is cost/)).toBeTruthy();
    expect(screen.getByText("−KES 1,000")).toBeTruthy();
    expect(screen.getByText("Net (loss)")).toBeTruthy();
  });

  it("does not claim the cull rule when the purpose is fattening", async () => {
    call.mockImplementationOnce(async () => ({ ok: true, ...econ({ purpose: "Fattening", kept_as_cost: false }) }));
    render(<BullPanel animal="B001/22" />);
    await waitFor(() => expect(screen.getByText(/Purpose: Fattening/)).toBeTruthy());
    expect(screen.queryByText(/every day he is kept is cost/)).toBeNull();
  });
});

describe("the animal list", () => {
  beforeEach(() => window.localStorage.clear());
  const animals = [mk("A1", "Female", "Steamers"), mk("B001/22", "Male", "Steamers"), mk("B2", "Male", "Calves")];

  it("shows feed against value on the selected bull only", () => {
    render(<AnimalSearch animals={animals} selectedId="B001/22" onSelect={() => {}} bulls={{ "B001/22": econ(), B2: econ({ animal: "B2" }) }} />);
    expect(screen.getAllByTestId("bull-burden")).toHaveLength(1);
    expect(screen.getByTestId("bull-burden").textContent).toContain("Burden since 2026-11-01");
  });

  it("shows it on every bull once Bulls is chosen, and asks for the figures", () => {
    const onBulls = vi.fn();
    render(<AnimalSearch animals={animals} selectedId={null} onSelect={() => {}} onBulls={onBulls} bulls={{ "B001/22": econ(), B2: econ({ animal: "B2" }) }} />);
    expect(screen.queryAllByTestId("bull-burden")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: /^Bulls/ }));
    expect(onBulls).toHaveBeenCalled();
    expect(screen.getAllByTestId("bull-burden")).toHaveLength(2);
  });
});

describe("pronouns follow the animal's sex", () => {
  it("he for a bull, she for a cow, it when unknown", async () => {
    const { pronouns } = await import("@/lib/animals");
    expect(pronouns("Male").poss).toBe("his");
    expect(pronouns("Female").subj).toBe("she");
    expect(pronouns(null).obj).toBe("it");
  });

  it("the timeline and feed do not call a bull her", async () => {
    const { EventFeed } = await import("@/components/animals/EventFeed");
    render(<EventFeed milestones={[]} sex="Male" />);
    expect(screen.getByText(/Nothing recorded against him yet/)).toBeTruthy();
  });
});
