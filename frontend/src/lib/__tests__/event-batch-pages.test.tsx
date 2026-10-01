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

const twoStoreDrug = () => ({
  ...drug,
  locations: [{ warehouse: "Store A", qty: 10 }, { warehouse: "Store B", qty: 4 }],
});

const plan = (tracked: boolean) => ({
  item_code: "DRUG-A", warehouse: "Store A", required_qty: 1, tracked,
  picks: tracked ? [{ batch_no: "B-1", qty: 1 }] : [], short: 0, blocked_by: [],
  available: tracked
    ? [{ batch_no: "B-1", qty: 9, expiry_date: null }, { batch_no: "B-2", qty: 5, expiry_date: null }]
    : [],
});

const state = vi.hoisted(() => ({
  tracked: true,
  held: false as boolean,
  /** When set, answers each event_batches request (and may delay it). */
  answer: null as null | ((lines: Array<{ item_code: string; warehouse: string }>) => unknown),
  twoStores: false,
}));

const perStore = (lines: Array<{ item_code: string; warehouse: string }>) =>
  lines.map((l) => ({
    item_code: l.item_code, warehouse: l.warehouse, required_qty: 1, tracked: true,
    picks: [], short: 0, blocked_by: [],
    available: [{ batch_no: `${l.warehouse}-LOT`, qty: 5, expiry_date: null }],
  }));

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  const m = method || "";
  if (m.includes("event_batches")) {
    if (state.answer) return state.answer(JSON.parse(String(args?.lines)));
    if (state.held) return new Promise(() => {});
    return { ok: true, lines: [plan(state.tracked)] };
  }
  if (m.includes("open_health_cases"))
    return { ok: true, cases: [], drug_items: [state.twoStores ? twoStoreDrug() : drug], routes: [], employee: "E1" };
  if (m.includes("health_options"))
    return { ok: true, animals: [{ name: "A1", label: "Daisy", herd: "H1", herd_label: "Herd 1" }],
      carrying: [], diseases: [], abortion_causes: [], appearances: [], hydrations: [], actions: [],
      case_statuses: [], severities: [], routes: [], employee: "E1" };
  if (m.includes("case_for_animal"))
    return { ok: true, animal: "A1", open_case: null, history: [], closed_count: 0 };
  if (m.includes("husbandry_options"))
    return { ok: true, animals: [{ name: "A1", label: "Daisy", herd: "H1", herd_label: "Herd 1" }],
      event_types: ["Vaccination"], drug_consuming_types: ["Vaccination"], drug_items: [state.twoStores ? twoStoreDrug() : drug],
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
  state.answer = null;
  state.twoStores = false;
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

const batchCalls = () => call.mock.calls.filter(([m]) => (m || "").includes("event_batches"));
const asked = (i: number) => JSON.parse(String(batchCalls()[i][1]?.lines)) as Array<Record<string, unknown>>;

async function pickAlpha(nth = 0) {
  fireEvent.click(screen.getAllByLabelText("Item")[nth]);
  fireEvent.click(await screen.findByRole("option", { name: /Alpha/ }));
}

async function moveToStoreB(nth: number) {
  fireEvent.click(screen.getAllByLabelText("From store")[nth]);
  fireEvent.click(await screen.findByRole("option", { name: /Store B/ }));
}

describe("the plan belongs to the item AND the store", () => {
  it("gives two rows of the same item in different stores each its own batches", async () => {
    state.twoStores = true;
    state.answer = (lines) => ({ ok: true, lines: perStore(lines) });
    wrap(<Husbandry />);
    await waitFor(() => expect(screen.getAllByLabelText("Item").length).toBe(1));
    await pickAlpha(0);
    fireEvent.click(screen.getByText("Another item"));
    await waitFor(() => expect(screen.getAllByLabelText("Item").length).toBe(2));
    await pickAlpha(1);
    await moveToStoreB(1);
    await waitFor(() => expect(screen.getAllByLabelText("Batch").length).toBe(2));

    fireEvent.click(screen.getAllByLabelText("Batch")[0]);
    expect(await screen.findByRole("option", { name: /Store A - LOT|Store A-LOT/ })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /Store B-LOT/ })).toBeNull();
  });

  it("drops the old store's plan the moment the store changes", async () => {
    state.twoStores = true;
    state.answer = (lines) => ({ ok: true, lines: perStore(lines) });
    wrap(<Husbandry />);
    await waitFor(() => expect(screen.getByLabelText("Item")).toBeTruthy());
    await pickAlpha(0);
    expect(await screen.findByLabelText("Batch")).toBeTruthy();
    // The next answer never arrives: nothing must be offered meanwhile.
    state.answer = () => new Promise(() => {});
    await moveToStoreB(0);
    await waitFor(() => expect(screen.queryByLabelText("Batch")).toBeNull());
  });

  it("shows nothing, rather than a stale answer, when the new request fails", async () => {
    state.twoStores = true;
    state.answer = (lines) => ({ ok: true, lines: perStore(lines) });
    wrap(<Husbandry />);
    await waitFor(() => expect(screen.getByLabelText("Item")).toBeTruthy());
    await pickAlpha(0);
    expect(await screen.findByLabelText("Batch")).toBeTruthy();
    state.answer = () => ({ error: "unreachable" });
    await moveToStoreB(0);
    await waitFor(() => expect(screen.queryByLabelText("Batch")).toBeNull());
    expect(screen.queryByText("not batched")).toBeNull();
  });

  it("does not let a slow first answer overwrite a newer one", async () => {
    state.twoStores = true;
    let late!: () => void;
    state.answer = (lines) =>
      new Promise((resolve) => {
        late = () => resolve({ ok: true, lines: perStore(lines) });
      });
    wrap(<Husbandry />);
    await waitFor(() => expect(screen.getByLabelText("Item")).toBeTruthy());
    await pickAlpha(0);
    await waitFor(() => expect(batchCalls().length).toBe(1));
    const first = late; // Store A's answer, held back.
    await moveToStoreB(0);
    await waitFor(() => expect(batchCalls().length).toBe(2));
    late(); // Store B's answer lands first.
    expect(await screen.findByLabelText("Batch")).toBeTruthy();
    first(); // Then Store A's, late.
    await new Promise((r) => setTimeout(r, 30));
    fireEvent.click(screen.getByLabelText("Batch"));
    expect(await screen.findByRole("option", { name: /Store B-LOT/ })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /Store A-LOT/ })).toBeNull();
  });

  it("asks nothing until a row has both an item and a store", async () => {
    wrap(<Husbandry />);
    await waitFor(() => expect(screen.getByLabelText("Item")).toBeTruthy());
    await new Promise((r) => setTimeout(r, 30));
    expect(batchCalls().length).toBe(0);
  });

  it("does not ask again for every keystroke in the quantity", async () => {
    wrap(<Husbandry />);
    await waitFor(() => expect(screen.getByLabelText("Item")).toBeTruthy());
    await pickAlpha(0);
    await waitFor(() => expect(batchCalls().length).toBe(1));
    fireEvent.change(screen.getByLabelText("Qty"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Qty"), { target: { value: "25" } });
    await new Promise((r) => setTimeout(r, 30));
    expect(batchCalls().length).toBe(1);
    expect(asked(0)[0].warehouse).toBe("Store A");
  });
});
