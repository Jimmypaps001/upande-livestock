import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * A feed run says who gave it, and its answer comes up at the bottom of the
 * screen, by the button — not in a banner at the top somebody has to scroll
 * back up to.
 */

const state = vi.hoisted(() => ({
  run: { ok: true } as Record<string, unknown>,
  sent: [] as Record<string, unknown>[],
}));

const program = {
  ok: true,
  herd: "H1",
  herd_label: "Lactating group 1",
  bom_no: "BOM-1",
  production_item: "RATION",
  production_item_name: "Lactating Ration",
  heads: 10,
  per_head_qty: 18,
  total_manufacture_qty: 180,
  uom: "Kg",
  store: "Feed Store",
  available_in_store: 0,
  lines: [],
  shortages: [],
  concentrates: [],
  can_manufacture: true,
  warehouses: [],
};

const call = vi.fn(async (method?: string, args?: { payload?: Record<string, unknown> }) => {
  const m = method || "";
  const action = args?.payload?.action;
  if (m.includes("posting_day")) return { ok: true, today: "2026-10-06", backdating_open: false };
  if (m.includes("employee_options"))
    return {
      ok: true,
      mine: null,
      query: "",
      more: false,
      employees: [{ value: "HR-EMP-1", label: "JOSIAH KIPTOO", detail: "HR-EMP-1 · Herdsman" }],
    };
  if (m.includes("feed_options"))
    return { ok: true, herds: [{ name: "H1", label: "Lactating group 1", heads: 10, bom: "BOM-1" }] };
  if (m.includes("herd_recipes")) return { ok: true, recipes: [], standing_bom: "BOM-1" };
  if (m.includes("record_feeding") && action === "info") return program;
  if (m.includes("record_feeding") && action === "day") return { error: "no day" };
  if (m.includes("record_feeding") && action === "manufacture") {
    state.sent.push(args!.payload!);
    return state.run;
  }
  return { ok: true, lines: [], concentrates: [] };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Feeding } = await import("@/pages/Feeding");
const { ToastProvider } = await import("@/components/Toast");

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <Feeding />
      </ToastProvider>
    </TooltipProvider>,
  );

async function pickHerd() {
  fireEvent.click(await screen.findByLabelText("Herd"));
  fireEvent.click(await screen.findByRole("option", { name: "Lactating group 1" }));
}

async function pickOperator() {
  fireEvent.focus(await screen.findByLabelText("Who is recording this"));
  fireEvent.click(await screen.findByText("JOSIAH KIPTOO"));
}

/** The floating toasts, apart from the page. */
const toasts = () => document.querySelector(".fixed.bottom-3") as HTMLElement;

beforeEach(() => {
  state.sent = [];
  state.run = { ok: true };
  try {
    window.localStorage.clear();
  } catch {
    /* the page copes */
  }
});

describe("a feed run", () => {
  it("is attributed to the employee chosen in the search", async () => {
    state.run = {
      ok: true, work_order: "WO-1", issue_stock_entry: "STE-9", produced_qty: 90, issued_qty: 90, uom: "Kg",
      heads: 10, portion: 0.5,
    };
    draw();
    await pickHerd();
    await pickOperator();
    fireEvent.click(await screen.findByRole("button", { name: "Mix & feed" }));
    await waitFor(() => expect(state.sent).toHaveLength(1));
    expect(state.sent[0].employee).toBe("HR-EMP-1");
    expect(await within(toasts()).findByText(/Manufactured and issued 90/)).toBeTruthy();
  });

  it("puts a refusal in a toast at the bottom, not a banner at the top", async () => {
    state.run = { error: "No Employee is linked to your user (Administrator)." };
    draw();
    await pickHerd();
    fireEvent.click(await screen.findByRole("button", { name: "Mix & feed" }));
    expect(await within(toasts()).findByText(/No Employee is linked/)).toBeTruthy();
    // Said once, where the button is.
    expect(screen.getAllByText(/No Employee is linked/)).toHaveLength(1);
  });

  it("says what a run that waits for stock fed", async () => {
    state.run = {
      ok: true, pending: true, work_order: "WO-2", transfer_stock_entry: "STE-10", issue_stock_entry: "",
      produced_qty: 90, issued_qty: 0, uom: "Kg", heads: 10, portion: 0.5,
      waiting_for: "Not enough to mix RATION: Silage short 5.00 Kg",
    };
    draw();
    await pickHerd();
    fireEvent.click(await screen.findByRole("button", { name: "Mix & feed" }));
    // The page says what was fed; the draft itself is announced by the app
    // (lib/stock-drafts) — once, not twice.
    expect(await within(toasts()).findByText(/Fed 90.00 Kg to Lactating group 1 and recorded on Work Order WO-2/)).toBeTruthy();
    expect(within(toasts()).queryByText(/waits as a draft/)).toBeNull();
  });
});
