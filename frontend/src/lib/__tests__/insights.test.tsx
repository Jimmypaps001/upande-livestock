import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The read-only screens.
 *
 * Their whole job is to be legible and honest about what they do not know, so
 * what is tested is that they say "nothing yet" rather than drawing an empty
 * table, and that the counts they show are the ones the rest of the app uses.
 */

const payloads: Record<string, unknown> = {
  get_events: {
    ok: true,
    rows: [
      { name: "E1", animal: "A039/26", current_herd: "Lactating group 1", new_herd: "STEAMERS", event_type: "Movement", event_date: "2026-09-12" },
      { name: "E2", animal: "A101/23", current_herd: "Lactating group 2", new_herd: null, event_type: "Service", event_date: "2026-09-11" },
    ],
    summary: { total: 2, by_type: { Movement: 1, Service: 1 } },
    filters: { types: ["Movement", "Service"] },
  },
  get_production: { ok: true, rows: [], summary: { net_kg: 0, revenue: 0, discarded_kg: 0, records: 0 }, filters: {} },
  get_reports: {
    ok: true,
    production: { month_kg: 0, prev_kg: 5400, delta_kg: -5400, month_rev: 0, prev_rev: 0 },
    health: { active_animals: 371, open_cases: 8, cases_month: 0, open_rate: 2.2 },
    reproduction: { pregnant: 0, served: 1, open: 393, births_month: 4, preg_rate: 0 },
    herds: [
      { name: "12 MONTHS-SERVICE (BULLYING HEIFERS)", animals: 94 },
      { name: "Lactating group 1", animals: 69 },
    ],
  },
};

const call = vi.fn(async (method?: string) => {
  const key = Object.keys(payloads).find((k) => (method || "").includes(k));
  return key ? payloads[key] : { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Events, Production, Reports } = await import("@/pages/Insights");

const draw = (Page: () => React.ReactElement) =>
  render(
    <TooltipProvider>
      <ToastProvider>
      <Page />
    </ToastProvider>
    </TooltipProvider>,
  );

describe("the read-only screens", () => {
  beforeEach(() => call.mockClear());

  it("shows a move as where it came from and where it went", async () => {
    draw(Events);
    await waitFor(() => expect(screen.getByText("Lactating group 1 → STEAMERS")).toBeTruthy());
  });

  it("filters events by kind without asking the server again", async () => {
    draw(Events);
    // "Movement" is both a filter pill and a table cell, which is the point of
    // the screen — wait on the row, not the ambiguous word.
    await waitFor(() => expect(screen.getByText("Lactating group 1 → STEAMERS")).toBeTruthy());
    const before = call.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Service" }));
    await waitFor(() => expect(screen.queryByText("Lactating group 1 → STEAMERS")).toBeNull());
    expect(call.mock.calls.length).toBe(before);
  });

  it("says nothing has been milked rather than drawing an empty table", async () => {
    draw(Production);
    await waitFor(() =>
      expect(screen.getByText(/No milking has been recorded yet/)).toBeTruthy(),
    );
  });

  it("reports the herd counts the herd records use", async () => {
    // These disagreed until the report stopped counting animals that have left
    // the farm: 112 against the herd screen's 94.
    draw(Reports);
    await waitFor(() => expect(screen.getByText("94")).toBeTruthy());
    expect(screen.getByText("69")).toBeTruthy();
  });

  it("says which way production moved, not just the number", async () => {
    draw(Reports);
    // fmt() carries two decimals everywhere in this app, so the hint reads
    // "-5,400.00 on last month" — matched as rendered rather than as imagined.
    await waitFor(() =>
      expect(screen.getByText((t) => t.includes("5,400.00 on last month"))).toBeTruthy(),
    );
  });

  // The health screens moved out of this module: the tab is a dashboard now and
  // the files are their own register. Their tests live in health-files.test.tsx.
});
