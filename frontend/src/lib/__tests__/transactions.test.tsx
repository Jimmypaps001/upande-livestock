import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The stock the farm's records moved: every draft still waiting in the middle,
 * a small calendar on the right with an orange dot where a draft is waiting and
 * a green one where everything posted, and a day's own entries when it is
 * picked. A draft the store can cover is posted from here.
 */

/** The server's day, deliberately not the browser's. */
const SERVER_DAY = "2026-03-14";

const entry = (name: string, over: Record<string, unknown> = {}) => ({
  name,
  status: "Draft",
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

const state = vi.hoisted(() => ({
  drafts: [] as unknown[],
  day: [] as unknown[],
  days: {} as Record<string, { draft: number; posted: number }>,
  posted: [] as string[],
  asked: [] as string[],
}));

const call = vi.fn(async (method?: string, args?: { payload?: Record<string, string> }) => {
  const m = method || "";
  if (m.includes("posting_day")) return { ok: true, today: SERVER_DAY, backdating_open: false };
  if (m.includes("stock_drafts")) return { ok: true, drafts: state.drafts };
  if (m.includes("stock_calendar")) return { ok: true, days: state.days };
  if (m.includes("stock_day")) {
    state.asked.push(args?.payload?.date ?? "");
    return { ok: true, date: args?.payload?.date, entries: state.day };
  }
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

/** The calendar's cell for a day of the server's month. */
const dayCell = (n: number) =>
  document.querySelector(`td[data-day="2026-03-${String(n).padStart(2, "0")}"]`) as HTMLElement;

beforeEach(() => {
  state.drafts = [];
  state.day = [];
  state.days = {};
  state.posted = [];
  state.asked = [];
});

describe("Transactions", () => {
  it("opens on everything waiting", async () => {
    state.drafts = [entry("STE-1")];
    draw();
    expect(await screen.findByText("Waiting for stock")).toBeTruthy();
    expect(await screen.findByText("1 draft · 0 ready to post")).toBeTruthy();
    const list = screen.getByRole("list", { name: "Transactions" });
    expect(within(list).getByText("Livestock Vaccination")).toBeTruthy();
    expect(within(list).getByText("Still short: FMD Vaccine: need 2 Nos, store has 0")).toBeTruthy();
  });

  it("dots a day orange while a draft waits and green when everything posted", async () => {
    state.days = { "2026-03-10": { draft: 1, posted: 2 }, "2026-03-11": { draft: 0, posted: 3 } };
    draw();
    await waitFor(() => expect(dayCell(10)?.className).toContain("sd-data-amber"));
    expect(dayCell(11).className).toContain("sd-data-green");
    expect(dayCell(12).className).not.toMatch(/sd-data-(amber|green)/);
  });

  it("lists a picked day's drafts and posted entries, and goes back to everything waiting", async () => {
    state.drafts = [entry("STE-1")];
    state.day = [
      entry("STE-1"),
      entry("STE-2", { status: "Posted", can_post: false, short: null, stock_entry_type: "Livestock Deworming" }),
    ];
    draw();
    await waitFor(() => expect(dayCell(14)).toBeTruthy());
    fireEvent.click(within(dayCell(14)).getByRole("button"));
    expect(await screen.findByText("2 transactions · 1 in draft")).toBeTruthy();
    expect(state.asked).toContain(SERVER_DAY);
    const list = screen.getByRole("list", { name: "Transactions" });
    expect(within(list).getByText("Posted")).toBeTruthy();
    // A posted entry has nothing to post.
    expect(within(list).getAllByRole("button", { name: "Post" })).toHaveLength(1);
    fireEvent.click(await screen.findByRole("button", { name: /Everything waiting \(1\)/ }));
    expect(await screen.findByText("1 draft · 0 ready to post")).toBeTruthy();
  });

  it("will not post a draft the store cannot cover", async () => {
    state.drafts = [entry("STE-1")];
    draw();
    const button = await screen.findByRole("button", { name: "Post" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("posts a covered draft and reads the list again", async () => {
    state.drafts = [entry("STE-2", { can_post: true, short: null })];
    draw();
    fireEvent.click(await screen.findByRole("button", { name: "Post" }));
    await waitFor(() => expect(state.posted).toEqual(["STE-2"]));
    expect(await screen.findByText(/STE-2 posted/)).toBeTruthy();
    expect(call.mock.calls.filter(([m]) => String(m).includes("stock_drafts")).length).toBeGreaterThan(1);
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
