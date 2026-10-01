import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * A batch chosen on an event screen reaches the server.
 *
 * The Items table grew a Batch column; without the pages asking
 * `event_batches` and sending the answer, an event consuming a batch-tracked
 * drug could still not post.
 */

const drug = {
  value: "DRUG-A", label: "Alpha · 10 Litre in Store A", item_name: "Alpha", qty: 10, uom: "Litre",
  warehouse: "Store A", locations: [{ warehouse: "Store A", qty: 10 }],
};

const plan = (tracked: boolean) => ({
  item_code: "DRUG-A", warehouse: "Store A", required_qty: 1, tracked,
  picks: tracked ? [{ batch_no: "B-1", qty: 1 }] : [], short: 0, blocked_by: [],
  available: tracked
    ? [{ batch_no: "B-1", qty: 9, expiry_date: null }, { batch_no: "B-2", qty: 5, expiry_date: null }]
    : [],
});

const state = vi.hoisted(() => ({ tracked: true, held: false as boolean }));

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  const m = method || "";
  void args;
  if (m.includes("event_batches")) {
    if (state.held) return new Promise(() => {});
    return { ok: true, lines: [plan(state.tracked)] };
  }
  if (m.includes("open_health_cases"))
    return { ok: true, cases: [], drug_items: [drug], routes: [], employee: "E1" };
  if (m.includes("health_options"))
    return { ok: true, animals: [{ name: "A1", label: "Daisy", herd: "H1", herd_label: "Herd 1" }],
      carrying: [], diseases: [], abortion_causes: [], appearances: [], hydrations: [], actions: [],
      case_statuses: [], severities: [], routes: [], employee: "E1" };
  if (m.includes("case_for_animal"))
    return { ok: true, animal: "A1", open_case: null, history: [], closed_count: 0 };
  if (m.includes("husbandry_options"))
    return { ok: true, animals: [{ name: "A1", label: "Daisy", herd: "H1", herd_label: "Herd 1" }],
      event_types: ["Vaccination"], drug_consuming_types: ["Vaccination"], drug_items: [drug],
      drug_warehouse: null, herds: [], employee: "E1" };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Treatment } = await import("@/pages/Treatment");
const { Husbandry } = await import("@/pages/Husbandry");

const wrap = (el: React.ReactNode) =>
  render(
    <TooltipProvider>
      <ToastProvider>{el}</ToastProvider>
    </TooltipProvider>,
  );

const sentTo = (name: string) =>
  call.mock.calls.filter(([m]) => (m || "").includes(name)).at(-1)?.[1] as
    | { payload: Record<string, unknown> }
    | undefined;

async function chooseDrugAndBatch() {
  await waitFor(() => expect(screen.getByLabelText("Item")).toBeTruthy());
  fireEvent.click(screen.getByLabelText("Item"));
  fireEvent.click(await screen.findByRole("option", { name: /Alpha/ }));
  fireEvent.change(screen.getByLabelText("Qty"), { target: { value: "1" } });
  fireEvent.click(await screen.findByLabelText("Batch"));
  fireEvent.click(await screen.findByRole("option", { name: /B-2/ }));
}

beforeEach(() => {
  call.mockClear();
  state.tracked = true;
  state.held = false;
});

describe("Treatment sends the batch it was given", () => {
  it("puts batch_no on the treatment row", async () => {
    wrap(<Treatment />);
    fireEvent.click(await screen.findByText("Daisy"));
    fireEvent.change(await screen.findByLabelText("What is wrong"), { target: { value: "Limping" } });
    await chooseDrugAndBatch();
    fireEvent.click(screen.getByRole("button", { name: /Open a file and record it/ }));
    await waitFor(() => expect(sentTo("treat_animal")).toBeTruthy());
    const rows = sentTo("treat_animal")!.payload.treatments as Array<Record<string, unknown>>;
    expect(rows[0].batch_no).toBe("B-2");
    expect(rows[0].source_warehouse).toBe("Store A");
  });

  it("says nothing about batches while the plan is still in flight", async () => {
    state.held = true;
    wrap(<Treatment />);
    await waitFor(() => expect(screen.getByLabelText("Item")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("Item"));
    fireEvent.click(await screen.findByRole("option", { name: /Alpha/ }));
    await waitFor(() => expect(sentTo("event_batches")).toBeTruthy());
    expect(screen.queryByText("not batched")).toBeNull();
    expect(screen.queryByLabelText("Batch")).toBeNull();
  });
});

describe("Husbandry sends the batch it was given", () => {
  it("puts batch_no on the drug row", async () => {
    wrap(<Husbandry />);
    fireEvent.click(await screen.findByText("Daisy"));
    await chooseDrugAndBatch();
    fireEvent.click(screen.getByRole("button", { name: /Record Vaccination/ }));
    await waitFor(() => expect(sentTo("create_husbandry_event")).toBeTruthy());
    const rows = sentTo("create_husbandry_event")!.payload.drugs as Array<Record<string, unknown>>;
    expect(rows[0].batch_no).toBe("B-2");
  });

  it("says 'not batched' only once the answer says so", async () => {
    state.tracked = false;
    wrap(<Husbandry />);
    await waitFor(() => expect(screen.getByLabelText("Item")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("Item"));
    fireEvent.click(await screen.findByRole("option", { name: /Alpha/ }));
    expect(await screen.findByText("not batched")).toBeTruthy();
  });
});
