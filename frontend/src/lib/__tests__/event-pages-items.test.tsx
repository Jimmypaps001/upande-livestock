import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Heat, Abortion, Diagnosis and Calving carry the Items table, each reading
 * the list of ITS OWN event type out of `items_by_event`.
 */

const drug = (code: string, name: string) => ({
  value: code, label: `${name} · 10 Litre in Store A`, item_name: name, qty: 10, uom: "Litre",
  warehouse: "Store A", locations: [{ warehouse: "Store A", qty: 10 }],
});

const state = vi.hoisted(() => ({
  /** undefined = the payload carries no items_by_event at all. */
  byEvent: undefined as undefined | Record<string, unknown[]>,
}));

const plan = {
  item_code: "HEAT-DRUG", warehouse: "Store A", required_qty: 1, tracked: true,
  picks: [], short: 0, blocked_by: [],
  available: [{ batch_no: "B-1", qty: 9, expiry_date: null }, { batch_no: "B-2", qty: 5, expiry_date: null }],
};

const cow = { name: "A1", label: "Daisy", herd: "H1", herd_label: "Herd 1", repro: null };

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.includes("event_batches")) {
    const lines = JSON.parse(String(args?.lines)) as Array<{ item_code: string }>;
    return { ok: true, lines: lines.map((l) => ({ ...plan, item_code: l.item_code })) };
  }
  const items = state.byEvent ? { items_by_event: state.byEvent } : {};
  if (m.includes("breeding_options"))
    return { ok: true, animals: [], diagnosis_animals: [cow], heat_animals: [cow], service_types: [],
      diagnosis_results: ["Confirmed"], sires: [], semen_items: [], employee: "E1", ...items };
  if (m.includes("health_options"))
    return { ok: true, animals: [cow], carrying: [cow], abortion_causes: ["Disease"], employee: "E1", ...items };
  if (m.includes("event_options"))
    return { ok: true, animals: [], dry_off_animals: [], calving_animals: [cow], herds: [],
      calving_outcomes: [], dry_off_herd: null, employee: "E1", ...items };
  if (m.includes("calving_destinations"))
    return { ok: true, dam: { from_herd: "H1", to_herd: "H2", will_move: true, reason: "r" },
      female_calf: { to_herd: "H3", reason: "r" }, male_calf: { to_herd: "H4", reason: "r" } };
  return { ok: true, name: "EV-1", calves: [] };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Heat, Abortion } = await import("@/pages/Breeding");
const { Calving } = await import("@/pages/Calving");

const wrap = (el: React.ReactNode) =>
  render(
    <TooltipProvider>
      <ToastProvider>{el}</ToastProvider>
    </TooltipProvider>,
  );

const sent = (name: string) =>
  call.mock.calls.filter(([m]) => (m || "").includes(name)).at(-1)?.[1] as
    | { payload: Record<string, unknown> }
    | undefined;

async function useItem(name: RegExp, qty = "3", batch = /B-2/) {
  fireEvent.click(await screen.findByLabelText("Item"));
  fireEvent.click(await screen.findByRole("option", { name }));
  fireEvent.change(screen.getByLabelText("Qty"), { target: { value: qty } });
  fireEvent.click(await screen.findByLabelText("Batch"));
  fireEvent.click(await screen.findByRole("option", { name: batch }));
}

beforeEach(() => {
  call.mockClear();
  state.byEvent = {
    "Heat Detection": [drug("HEAT-DRUG", "Heat Drug")],
    "Pregnancy Diagnosis": [drug("DIAG-DRUG", "Diag Drug")],
    Abortion: [drug("ABORT-DRUG", "Abort Drug")],
    Calving: [drug("CALF-DRUG", "Calf Drug")],
  };
});

describe("each screen reads its own event type's list", () => {
  it("Heat sends item, qty, store and batch", async () => {
    wrap(<Heat />);
    fireEvent.click(await screen.findByText("Daisy"));
    await useItem(/Heat Drug/);
    fireEvent.click(screen.getByRole("button", { name: "Record the heat" }));
    await waitFor(() => expect(sent("create_heat_event")).toBeTruthy());
    expect(sent("create_heat_event")!.payload.items).toEqual([
      { item_code: "HEAT-DRUG", qty: 3, source_warehouse: "Store A", batch_no: "B-2" },
    ]);
  });

  it("Abortion offers Abortion's items only", async () => {
    wrap(<Abortion />);
    fireEvent.click(await screen.findByText("Daisy"));
    fireEvent.click(await screen.findByLabelText("Item"));
    expect(await screen.findByRole("option", { name: /Abort Drug/ })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /Heat Drug|Calf Drug/ })).toBeNull();
  });

  it("Abortion sends the items on its payload", async () => {
    wrap(<Abortion />);
    fireEvent.click(await screen.findByText("Daisy"));
    await useItem(/Abort Drug/, "1", /B-1/);
    fireEvent.click(screen.getByRole("button", { name: "Record the loss" }));
    await waitFor(() => expect(sent("create_abortion_event")).toBeTruthy());
    expect(sent("create_abortion_event")!.payload.items).toEqual([
      { item_code: "ABORT-DRUG", qty: 1, source_warehouse: "Store A", batch_no: "B-1" },
    ]);
  });

  it("Calving sends the items to record_birth", async () => {
    wrap(<Calving />);
    fireEvent.click(await screen.findByText("Daisy"));
    await useItem(/Calf Drug/);
    fireEvent.click(await screen.findByRole("button", { name: /Record the calving/ }));
    await waitFor(() => expect(sent("record_birth")).toBeTruthy());
    expect(sent("record_birth")!.payload.items).toEqual([
      { item_code: "CALF-DRUG", qty: 3, source_warehouse: "Store A", batch_no: "B-2" },
    ]);
  });

  it("an event type absent from the payload shows nothing, not 'nothing is mapped'", async () => {
    state.byEvent = undefined;
    wrap(<Heat />);
    fireEvent.click(await screen.findByText("Daisy"));
    await screen.findByRole("button", { name: "Record the heat" });
    expect(screen.queryByLabelText("Item")).toBeNull();
    expect(screen.queryByText(/No items are mapped/)).toBeNull();
  });

  it("a mapped-to-nothing type says so", async () => {
    state.byEvent = { "Heat Detection": [] };
    wrap(<Heat />);
    fireEvent.click(await screen.findByText("Daisy"));
    expect(await screen.findByText(/No items are mapped/)).toBeTruthy();
  });
});
