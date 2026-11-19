import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The Feeding day sheet and the Daily Feed Report: a herd's day loads from its
 * recipe, Amend sends only the kilograms changed, Mix sends the chosen
 * operator, and the report reads planned against fed per animal.
 */

const state = vi.hoisted(() => ({
  sent: [] as Array<{ method: string; args: Record<string, unknown> }>,
  status: "Planned",
}));

const comps = () => [
  { item_code: "SIL", item_name: "Silage", uom: "Kilogram", planned_kg: 900, actual_kg: 900, planned_per_head: 10, actual_per_head: 10, removed: false },
  { item_code: "CON", item_name: "Dairy meal", uom: "Kilogram", planned_kg: 90, actual_kg: 90, planned_per_head: 1, actual_per_head: 1, removed: false },
];
const herdDay = () => ({
  herd: "H1", herd_name: "Lactating group 1", date: "2026-11-19", record: null, bom: "BOM-1",
  head_count: 90, status: state.status, amended: false, planned_kg: 990, actual_kg: 990,
  planned_per_head: 11, actual_per_head: 11, variance_kg: 0, components: comps(),
  draft_entries: [], remarks: null,
});

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  const m = method || "";
  state.sent.push({ method: m, args: args || {} });
  if (m.endsWith("feed_day_program")) return { ok: true, date: "2026-11-19", herds: [herdDay()], skipped: [], setup: [] };
  if (m.endsWith("amend_feed_day")) return { ok: true, ...herdDay(), amended: true, status: "Amended" };
  if (m.endsWith("manufacture_feed_actuals")) return { ok: true, ...herdDay(), status: "Manufactured", pending: false };
  if (m.endsWith("daily_feed_report"))
    return {
      ok: true, date: "2026-11-19",
      herds: [{ herd: "H1", herd_name: "Lactating group 1", head_count: 90, planned_kg: 990, actual_kg: 1080, amended: true, draft_entries: [], components: [] }],
      animals: [{ animal: "A1", tag: "0001", herd: "H1", planned_kg: 11, actual_kg: 12, variance_kg: 1, variance_pct: 9.1, appetite: "above", last_weight: 500, last_weight_date: "2026-11-01", adg: 0.8 }],
      totals: { planned_kg: 990, actual_kg: 1080, below_plan: 0, above_plan: 1, on_plan: 0 },
    };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { FeedDay } = await import("@/components/feeding/FeedDay");
const { FeedReport } = await import("@/pages/FeedReport");
const { ToastProvider } = await import("@/components/Toast");

const wrap = (ui: React.ReactNode) =>
  render(
    <TooltipProvider>
      <ToastProvider>{ui}</ToastProvider>
    </TooltipProvider>,
  );

beforeEach(() => {
  window.LIVESTOCK = { bootstrap: { roles: ["System Manager"] } };
  state.sent = [];
  state.status = "Planned";
  call.mockClear();
});

describe("the feeding day sheet", () => {
  it("loads each herd's day from its recipe: planned beside fed", async () => {
    wrap(<FeedDay />);
    expect(await screen.findByText("Lactating group 1")).toBeTruthy();
    expect(await screen.findByText("Silage")).toBeTruthy();
    expect(screen.getByText("Dairy meal")).toBeTruthy();
  });

  it("Amend sends the kilograms fed for that herd and day", async () => {
    wrap(<FeedDay />);
    fireEvent.click(await screen.findByRole("button", { name: "Amend" }));
    const silage = (await screen.findByDisplayValue("900")) as HTMLInputElement;
    fireEvent.change(silage, { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save what was fed" }));
    await waitFor(() => expect(state.sent.some((s) => s.method.endsWith("amend_feed_day"))).toBe(true));
    const sent = state.sent.find((s) => s.method.endsWith("amend_feed_day"))!;
    expect(sent.args.herd).toBe("H1");
    expect(String(sent.args.components)).toContain("SIL");
    expect(String(sent.args.components)).toContain("1000");
  });

  it("an X drops an item not used by sending it as 0", async () => {
    wrap(<FeedDay />);
    fireEvent.click(await screen.findByRole("button", { name: "Amend" }));
    fireEvent.click(await screen.findByRole("button", { name: "Remove Dairy meal, not used today" }));
    fireEvent.click(screen.getByRole("button", { name: "Save what was fed" }));
    await waitFor(() => expect(state.sent.some((s) => s.method.endsWith("amend_feed_day"))).toBe(true));
    const sent = state.sent.find((s) => s.method.endsWith("amend_feed_day"))!;
    expect(JSON.stringify(sent.args.components)).toMatch(/CON[^}]*0/);
  });

  it("Mix sends the operator chosen at the top", async () => {
    wrap(<FeedDay employee="HR-EMP-1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Mix and issue what was fed/ }));
    await waitFor(() => expect(state.sent.some((s) => s.method.endsWith("manufacture_feed_actuals"))).toBe(true));
    expect(state.sent.find((s) => s.method.endsWith("manufacture_feed_actuals"))!.args.employee).toBe("HR-EMP-1");
  });

  it("a user with no Employee who may not pick one has the buttons off", async () => {
    wrap(<FeedDay blocked="You're not registered as an employee, so you can't record." />);
    const amend = (await screen.findByRole("button", { name: "Amend" })) as HTMLButtonElement;
    expect(amend.disabled).toBe(true);
  });
});

describe("the daily feed report", () => {
  it("shows planned against fed and the animals' appetite", async () => {
    wrap(<FeedReport />);
    expect(await screen.findByText("Lactating group 1")).toBeTruthy();
    expect(await screen.findByText("0001")).toBeTruthy();
    expect(state.sent.some((s) => s.method.endsWith("daily_feed_report"))).toBe(true);
  });
});
