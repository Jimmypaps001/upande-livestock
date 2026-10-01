import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Any record-an-event screen can carry the Items table.
 *
 * `itemsOf` is what an event type's mapping gave the screen. The table sends
 * item, quantity, store AND batch: a batch-tracked item cannot post without
 * one, so a payload that dropped it would fail at ERPNext, not here.
 */

const drug = {
  value: "DRUG-A", label: "Alpha · 10 Litre in Store A", item_name: "Alpha", qty: 10, uom: "Litre",
  warehouse: "Store A", locations: [{ warehouse: "Store A", qty: 10 }],
};

const plan = {
  item_code: "DRUG-A", warehouse: "Store A", required_qty: 1, tracked: true,
  picks: [], short: 0, blocked_by: [],
  available: [{ batch_no: "B-1", qty: 9, expiry_date: null }, { batch_no: "B-2", qty: 5, expiry_date: null }],
};

const call = vi.fn(async (method?: string) => {
  if ((method || "").includes("event_batches")) return { ok: true, lines: [plan] };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { RecordEvent } = await import("@/components/events/RecordEvent");

interface O { animals: never[]; items?: (typeof drug)[] }

const options = {
  ok: true as const,
  animals: [{ name: "A1", label: "Daisy", herd: "H1", herd_label: "Herd 1", repro: null }],
};

const submit = vi.fn(async (_p: Record<string, unknown>) => ({ ok: true as const, name: "EV-1" }));

function screenWith(itemsOf?: (o: unknown) => (typeof drug)[] | undefined) {
  return render(
    <TooltipProvider>
      <ToastProvider>
        <RecordEvent<unknown>
          eyebrow="Breeding" title="a heat" blurb="b" pickLabel="Which" emptyPick="none"
          load={async () => options as never}
          animalsOf={() => options.animals as never}
          fieldsOf={() => []}
          submitLabel="Record heat"
          submit={submit}
          said={() => "done"}
          itemsOf={itemsOf as never}
        />
      </ToastProvider>
    </TooltipProvider>,
  );
}

beforeEach(() => {
  call.mockClear();
  submit.mockClear();
});

describe("RecordEvent with itemsOf", () => {
  it("sends item, qty, store and the chosen batch", async () => {
    screenWith(() => [drug]);
    fireEvent.click(await screen.findByText("Daisy"));
    fireEvent.click(await screen.findByLabelText("Item"));
    fireEvent.click(await screen.findByRole("option", { name: /Alpha/ }));
    fireEvent.change(screen.getByLabelText("Qty"), { target: { value: "2" } });
    fireEvent.click(await screen.findByLabelText("Batch"));
    fireEvent.click(await screen.findByRole("option", { name: /B-2/ }));
    fireEvent.click(screen.getByRole("button", { name: "Record heat" }));
    await waitFor(() => expect(submit).toHaveBeenCalled());
    expect(submit.mock.calls[0][0].items).toEqual([
      { item_code: "DRUG-A", qty: 2, source_warehouse: "Store A", batch_no: "B-2" },
    ]);
  });

  it("sends no batch_no key value at all when none was chosen, never an empty string", async () => {
    screenWith(() => [drug]);
    fireEvent.click(await screen.findByText("Daisy"));
    fireEvent.click(await screen.findByLabelText("Item"));
    fireEvent.click(await screen.findByRole("option", { name: /Alpha/ }));
    fireEvent.click(screen.getByRole("button", { name: "Record heat" }));
    await waitFor(() => expect(submit).toHaveBeenCalled());
    const rows = submit.mock.calls[0][0].items as Array<Record<string, unknown>>;
    expect(rows).toHaveLength(1);
    expect(rows[0].batch_no).toBeUndefined();
  });

  it("drops a blank row and sends an empty list when nothing was used", async () => {
    screenWith(() => [drug]);
    fireEvent.click(await screen.findByText("Daisy"));
    await screen.findByLabelText("Item");
    fireEvent.click(screen.getByRole("button", { name: "Record heat" }));
    await waitFor(() => expect(submit).toHaveBeenCalled());
    expect(submit.mock.calls[0][0].items).toEqual([]);
  });

  it("renders nothing while the list is not loaded, and says so only for an explicit empty one (mapped, nothing in stock)", async () => {
    const { unmount } = screenWith(() => undefined);
    fireEvent.click(await screen.findByText("Daisy"));
    await screen.findByRole("button", { name: "Record heat" });
    expect(screen.queryByLabelText("Item")).toBeNull();
    expect(screen.queryByText(/Nothing mapped to this event is in stock right now/)).toBeNull();
    unmount();

    screenWith(() => []);
    fireEvent.click(await screen.findByText("Daisy"));
    expect(await screen.findByText(/Nothing mapped to this event is in stock right now/)).toBeTruthy();
  });

  it("is absent altogether on a screen that passed no itemsOf", async () => {
    screenWith(undefined);
    fireEvent.click(await screen.findByText("Daisy"));
    await screen.findByRole("button", { name: "Record heat" });
    expect(screen.queryByLabelText("Item")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Record heat" }));
    await waitFor(() => expect(submit).toHaveBeenCalled());
    expect(submit.mock.calls[0][0].items).toBeUndefined();
  });
});
