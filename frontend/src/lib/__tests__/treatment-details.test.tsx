import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * A dose's details belong to the drug they were typed for. A withdrawal period
 * left behind when the drug changes is shown under the new drug's name, and
 * milk goes to the tank on the old drug's date.
 */

const state = vi.hoisted(() => ({
  drugs: [] as unknown[],
  gate: null as Promise<void> | null,
  fail: false,
  mapped: true,
}));

const drug = (value: string, name: string) => ({
  value, label: `${name} · 10 Litre in Store A`, item_name: name, qty: 10, uom: "Litre",
  warehouse: "Store A", locations: [{ warehouse: "Store A", qty: 10 }],
});

const call = vi.fn(async (method?: string) => {
  const m = method || "";
  if (m.includes("open_health_cases")) {
    if (state.gate) await state.gate;
    if (state.fail) return { error: "The store is unreachable." };
  }
  if (m.includes("open_health_cases"))
    return { ok: true, cases: [], drug_items: state.drugs, drug_items_mapped: state.mapped, routes: [], employee: "E1" };
  if (m.includes("health_options"))
    return { ok: true, animals: [], carrying: [], diseases: [], abortion_causes: [], appearances: [],
      hydrations: [], actions: [], case_statuses: [], severities: [], routes: [], employee: "E1" };
  // The batch endpoint answers with a `lines` array. Returning a bare `ok`
  // here made the hook read `.map` off undefined, which the run counted as an
  // unhandled rejection while every test still passed.
  if (m.includes("event_batches")) return { ok: true, lines: [] };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Treatment } = await import("@/pages/Treatment");

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <Treatment />
      </ToastProvider>
    </TooltipProvider>,
  );

describe("treatment details follow the drug", () => {
  it("drops a withdrawal period when the row's drug changes, keeps it when only the quantity does", async () => {
    state.drugs = [drug("DRUG-A", "Alpha"), drug("DRUG-B", "Beta")];
    draw();
    await waitFor(() => expect(screen.getByLabelText("Item")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("Item"));
    fireEvent.click(await screen.findByRole("option", { name: /Alpha/ }));
    const wd = () => screen.getByLabelText("Withdrawal (days)") as HTMLInputElement;
    await waitFor(() => expect(wd()).toBeTruthy());
    fireEvent.change(wd(), { target: { value: "7" } });
    expect(wd().value).toBe("7");

    fireEvent.change(screen.getByLabelText("Qty"), { target: { value: "3" } });
    expect(wd().value).toBe("7");

    fireEvent.click(screen.getByLabelText("Item"));
    fireEvent.click(await screen.findByRole("option", { name: /Beta/ }));
    await waitFor(() => expect(wd().value).toBe(""));
  });

  it("sends a farm that mapped nothing to Settings", async () => {
    state.drugs = [];
    state.mapped = false;
    state.gate = null;
    state.fail = false;
    draw();
    await waitFor(() => expect(screen.getByText(/not set to post stock/)).toBeTruthy());
    expect(screen.getByText(/Settings → Stock/)).toBeTruthy();
    expect(screen.queryByText(/in stock right now/)).toBeNull();
    state.mapped = true;
  });

  it("says the stock is out, not that nothing is mapped, when mapped and empty", async () => {
    state.drugs = [];
    state.mapped = true;
    state.gate = null;
    state.fail = false;
    draw();
    await waitFor(() =>
      expect(screen.getByText(/Nothing mapped to this event is in stock right now/)).toBeTruthy(),
    );
    expect(screen.queryByText(/not set to post stock/)).toBeNull();
    expect(screen.queryByText(/Settings/)).toBeNull();
  });

  it("does not claim nothing is in stock before the list has arrived, only once it is empty", async () => {
    let open!: () => void;
    state.gate = new Promise<void>((r) => (open = r));
    state.fail = false;
    state.drugs = [];
    draw();
    // Before the call resolves, and after the options have.
    expect(screen.queryByText(/Nothing mapped to this event is in stock right now/)).toBeNull();
    await waitFor(() => expect(call).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/Nothing mapped to this event is in stock right now/)).toBeNull();
    open();
    await waitFor(() => expect(screen.getByText(/Nothing mapped to this event is in stock right now/)).toBeTruthy());
    state.gate = null;
  });

  it("says the list could not be loaded, not that nothing is in stock, when the call fails", async () => {
    state.gate = null;
    state.fail = true;
    state.drugs = [];
    draw();
    await waitFor(() => expect(screen.getByText(/could not be loaded/)).toBeTruthy());
    expect(screen.queryByText(/Nothing mapped to this event is in stock right now/)).toBeNull();
    state.fail = false;
  });
});
