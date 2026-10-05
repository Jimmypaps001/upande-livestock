import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The stock the farm's records used that the store has not handed over: on a
 * calendar by the day it was recorded, and as a list, each posted from here
 * once the store can cover it.
 */

/** The server's day, deliberately not the browser's: drafts are dated by the
 *  server, and the calendar must open on its today. */
const SERVER_DAY = "2026-03-14";

const draft = (name: string, over: Record<string, unknown> = {}) => ({
  name,
  posting_date: SERVER_DAY,
  stock_entry_type: "Livestock Vaccination",
  remarks: null,
  made_by: "Vet One",
  source: { doctype: "Livestock Event", name: `VACC-${name}`, animal: "A001/20", event_type: "Vaccination" },
  items: [{ item_code: "FMD", item_name: "FMD Vaccine", qty: 2, uom: "Nos", warehouse: "Drug Store" }],
  can_post: false,
  short: "FMD Vaccine: need 2 Nos, store has 0",
  ...over,
});

const state = vi.hoisted(() => ({ drafts: [] as unknown[], posted: [] as string[] }));

const call = vi.fn(async (method?: string, args?: { payload?: { name?: string } }) => {
  const m = method || "";
  if (m.includes("posting_day")) return { ok: true, today: SERVER_DAY, backdating_open: false };
  if (m.includes("stock_drafts")) return { ok: true, drafts: state.drafts };
  if (m.includes("post_stock_draft")) {
    state.posted.push(args?.payload?.name ?? "");
    return { ok: true, name: args?.payload?.name };
  }
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Transactions } = await import("@/pages/Transactions");
const { ToastProvider } = await import("@/components/Toast");

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <Transactions />
      </ToastProvider>
    </TooltipProvider>,
  );

beforeEach(() => {
  state.drafts = [];
  state.posted = [];
});

describe("Transactions", () => {
  it("puts a draft on the day it was recorded and lists it under the calendar", async () => {
    state.drafts = [draft("STE-1")];
    draw();
    const day = await screen.findByRole("gridcell", { name: /1 draft$/ });
    expect(within(day).getByText(/Vaccination · A001\/20/)).toBeTruthy();
    // Opened on the server's today, so that day's draft is the one shown.
    await waitFor(() => expect(day.getAttribute("aria-selected")).toBe("true"));
    expect(await screen.findByText("Still short: FMD Vaccine: need 2 Nos, store has 0")).toBeTruthy();
    expect(screen.getByText("1 waiting · 0 ready to post")).toBeTruthy();
  });

  it("will not post a draft the store cannot cover", async () => {
    state.drafts = [draft("STE-1")];
    draw();
    const button = await screen.findByRole("button", { name: "Post" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("posts a covered draft and reads the list again", async () => {
    state.drafts = [draft("STE-2", { can_post: true, short: null })];
    draw();
    fireEvent.click(await screen.findByRole("button", { name: "Post" }));
    await waitFor(() => expect(state.posted).toEqual(["STE-2"]));
    expect(await screen.findByText(/STE-2 posted/)).toBeTruthy();
    expect(call.mock.calls.filter(([m]) => String(m).includes("stock_drafts")).length).toBeGreaterThan(1);
  });

  it("has a list of every draft", async () => {
    state.drafts = [draft("STE-1"), draft("STE-3", { posting_date: "2026-01-02", stock_entry_type: "Livestock Deworming" })];
    draw();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /List/ }));
    const table = await screen.findByRole("table", { name: "Draft stock entries" });
    expect(within(table).getByText("Livestock Deworming")).toBeTruthy();
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });

  it("says when nothing is waiting", async () => {
    draw();
    expect(await screen.findByText(/Nothing is waiting/)).toBeTruthy();
  });
});

describe("a record whose stock waits as a draft", () => {
  it("is announced by the toast whichever page made it", async () => {
    render(
      <ToastProvider>
        <div />
      </ToastProvider>,
    );
    act(() => {
      window.dispatchEvent(
        new CustomEvent("livestock:stock-drafts", {
          detail: [{ name: "STE-9", stock_entry_type: "Livestock Drying Off", short: "Tube: need 4 Nos, store has 0" }],
        }),
      );
    });
    expect(await screen.findByText(/STE-9 \(Livestock Drying Off\) is saved as a draft/)).toBeTruthy();
  });
});
