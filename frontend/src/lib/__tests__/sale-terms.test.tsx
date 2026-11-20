import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Selling a culled animal: choose the Customer and the invoice is composed.
 *
 * The endpoints are stood in for; what is pinned is what the form asks, what it
 * shows back, and that Approve waits on a complete draft.
 */

const preview = (over: Record<string, unknown> = {}) => ({
  ok: true,
  customer: {
    name: "Samwel Njoroge", customer_name: "Samwel Njoroge", customer_type: "Individual", tax_id: "A123456789B",
    mobile_no: "0712345678", email_id: null, customer_group: "Individual", territory: "Kenya", payment_terms: "14 days",
    default_currency: "KES", default_price_list: "Standard Selling", address: "Eldama Ravine", receivable: "Trade Debtors - KR", disabled: 0,
  },
  terms: {
    company: "Karen Roses", currency: "KES", price_list: "Standard Selling", payment_terms: "14 days", due_date: "2026-12-04",
    mode_of_payment: null, payment_type_code: "02", cost_center: "Dairy - KR", farm: "Karen", business_unit: "Westwood Milk",
    taxes_template: null, debit_to: "Trade Debtors - KR", amount: 90000, price_basis: "Per head", rate: null, weight_kg: null,
  },
  missing: [],
  notes: [],
  lines: [{ item_code: "herd", item_name: "herd", asset: "ACC-ASS-1", qty: 1, uom: "Nos", rate: 90000, amount: 90000,
    income_account: "Gain/Loss - KR", cost_center: "Dairy - KR" }],
  taxes: [],
  grand_total: 90000,
  tax_label: "No VAT rows (livestock sale)",
  weight_kg: 420,
  options: { payment_terms: ["0 days", "14 days"], modes_of_payment: ["Cash", "Mpesa-Karen Roses"] },
  ...over,
});

const sent: Array<{ method: string; args: Record<string, unknown> }> = [];
let answer: (method: string, args: Record<string, unknown>) => unknown;

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return {
    ...actual,
    call: vi.fn(async (method?: string, args?: Record<string, unknown>) => {
      sent.push({ method: method ?? "", args: args ?? {} });
      return answer(method ?? "", args ?? {});
    }),
  };
});

const { SaleTerms } = await import("@/components/culling/SaleTerms");
const { BuyerPicker } = await import("@/components/culling/BuyerPicker");
const { Culling } = await import("@/pages/Culling");
const { BLANK_SALE } = await import("@/lib/culling");
import { useState } from "react";

function Harness({ initial = BLANK_SALE, onReady = () => {} }: { initial?: typeof BLANK_SALE; onReady?: (r: boolean) => void }) {
  const [d, setD] = useState(initial);
  return <SaleTerms animal="A1" draft={d} onDraft={setD} onReady={onReady} />;
}

const caps = (manager: boolean) => ({
  read: { "Livestock Disposal": true }, create: { "Livestock Disposal": true }, write: { "Livestock Disposal": true },
  cull_manager: manager, cull_vet: false,
});

describe("the sale form", () => {
  beforeEach(() => {
    sent.length = 0;
    window.LIVESTOCK = { bootstrap: { user: "m@x.com", full_name: "M", roles: [], can: caps(true) } } as never;
    answer = (m) => (m.includes("buyer_search") ? { ok: true, buyers: [{ name: "Samwel Njoroge", customer_name: "Samwel Njoroge",
      customer_type: "Individual", tax_id: "A123456789B", mobile_no: "0712345678", payment_terms: "14 days" }] } : preview());
  });
  afterEach(() => {
    cleanup();
    delete window.LIVESTOCK;
  });

  it("asks nothing and is not ready until a buyer is chosen", async () => {
    const ready = vi.fn();
    render(<Harness onReady={ready} />);
    await waitFor(() => expect(ready).toHaveBeenCalledWith(false));
    expect(sent.some((c) => c.method.includes("sale_terms"))).toBe(false);
  });

  it("fetches the buyer's details and shows the invoice lines once a buyer is chosen", async () => {
    const ready = vi.fn();
    render(<Harness initial={{ ...BLANK_SALE, customer: "Samwel Njoroge", sale_price: "90000" }} onReady={ready} />);
    await waitFor(() => expect(screen.getByText("A123456789B")).toBeTruthy());
    expect(screen.getByText("0712345678")).toBeTruthy();
    expect(screen.getByText("Eldama Ravine")).toBeTruthy();
    expect(screen.getByLabelText("Invoice preview")).toBeTruthy();
    expect(screen.getByText("ACC-ASS-1")).toBeTruthy();
    expect(screen.getAllByText("90,000.00").length).toBeGreaterThan(1);
    await waitFor(() => expect(ready).toHaveBeenLastCalledWith(true));
    const asked = sent.find((c) => c.method.includes("sale_terms"))!;
    expect((asked.args.payload as Record<string, unknown>).customer).toBe("Samwel Njoroge");
    expect((asked.args.payload as Record<string, unknown>).sale_price).toBe(90000);
  });

  it("says what is missing in the server's words and stays not ready", async () => {
    answer = () => preview({ missing: ["Customer Samwel Njoroge has no receivable account for Karen Roses."], lines: [] });
    const ready = vi.fn();
    render(<Harness initial={{ ...BLANK_SALE, customer: "Samwel Njoroge", sale_price: "90000" }} onReady={ready} />);
    await waitFor(() => expect(screen.getByText(/no receivable account/)).toBeTruthy());
    expect(ready).toHaveBeenLastCalledWith(false);
    expect(screen.queryByLabelText("Invoice preview")).toBeNull();
  });

  it("prices per kg from a rate and the weight", async () => {
    render(<Harness initial={{ ...BLANK_SALE, customer: "Samwel Njoroge", price_basis: "Per kg", rate: "250" }} />);
    await waitFor(() => expect(screen.getByLabelText("Weight (kg)")).toBeTruthy());
    const asked = () => sent.filter((c) => c.method.includes("sale_terms")).at(-1)!.args.payload as Record<string, unknown>;
    await waitFor(() => expect(asked().rate).toBe(250));
    expect(asked().sale_price).toBeUndefined();
    fireEvent.change(screen.getByLabelText("Weight (kg)"), { target: { value: "400" } });
    await waitFor(() => expect(asked().weight_kg).toBe(400));
  });

  it("finds a buyer by typing and hands back the Customer", async () => {
    const chosen = vi.fn();
    render(<BuyerPicker value="" onChange={chosen} />);
    fireEvent.click(screen.getByRole("button", { name: "Buyer" }));
    fireEvent.change(await screen.findByLabelText("Search buyers"), { target: { value: "0712" } });
    fireEvent.click(await screen.findByText("Samwel Njoroge"));
    expect(chosen).toHaveBeenCalledWith("Samwel Njoroge");
    const asked = sent.filter((c) => c.method.includes("buyer_search")).at(-1)!;
    expect((asked.args.payload as Record<string, unknown>).term).toBe("0712");
  });

  it("adds a new buyer with a phone and a checked PIN, then selects it", async () => {
    answer = (m) => (m.includes("create_buyer") ? { ok: true, name: "Juma", existing: false } : { ok: true, buyers: [] });
    const chosen = vi.fn();
    render(<BuyerPicker value="" onChange={chosen} />);
    fireEvent.click(screen.getByRole("button", { name: /New buyer/ }));
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "Juma" } });
    fireEvent.click(screen.getByRole("button", { name: "Add buyer" }));
    expect(await screen.findByText(/phone number/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "0711222333" } });
    fireEvent.change(screen.getByLabelText(/KRA PIN/), { target: { value: "12345" } });
    fireEvent.click(screen.getByRole("button", { name: "Add buyer" }));
    expect(await screen.findByText(/looks like A123456789B/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/KRA PIN/), { target: { value: "a123456789b" } });
    fireEvent.click(screen.getByRole("button", { name: "Add buyer" }));
    await waitFor(() => expect(chosen).toHaveBeenCalledWith("Juma"));
    const made = sent.find((c) => c.method.includes("create_buyer"))!.args.payload as Record<string, unknown>;
    expect(made).toMatchObject({ customer_name: "Juma", phone: "0711222333", tax_id: "A123456789B" });
  });

  it("offers no New buyer button to someone who cannot approve a sale", () => {
    window.LIVESTOCK = { bootstrap: { user: "v@x.com", full_name: "V", roles: [], can: caps(false) } } as never;
    render(<BuyerPicker value="" onChange={() => {}} />);
    expect(screen.queryByRole("button", { name: /New buyer/ })).toBeNull();
  });
});

describe("approving a sale on the Culling page", () => {
  const board = {
    ok: true, animals: [], flagged: [], recent: [], open_claims: [],
    counts: { awaiting_vet: 0, awaiting_approval: 1, ready_to_post: 0, flagged: 0 },
    cases: [{
      name: "ANI-DISP-1", animal: "A057/22", animal_name: "NDAMA", herd: "Lactating group 1", disposal_date: "2026-11-20",
      disposal_type: "Sold", flow: "Sale", status: "Awaiting Approval", waiting_on: "the manager", evidence: "x",
      was_productive: false, death_cause: null, vet_verdict: "Fit for sale", vet_on: "2026-11-19", sale_price: 0,
      buyer_name: null, gifted_to: null,
    }],
  };
  beforeEach(() => {
    sent.length = 0;
    window.LIVESTOCK = { bootstrap: { user: "m@x.com", full_name: "M", roles: [], can: caps(true) } } as never;
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
    answer = (m) => {
      if (m.includes("cull_board")) return board;
      if (m.includes("sale_terms")) return preview();
      if (m.includes("approve_cull")) return { ok: true, name: "ANI-DISP-1", status: "Approved" };
      return { ok: true, buyers: [] };
    };
  });
  afterEach(() => {
    cleanup();
    delete window.LIVESTOCK;
  });

  function draw() {
    return render(
      <TooltipProvider>
        <ToastProvider>
          <Culling />
        </ToastProvider>
      </TooltipProvider>,
    );
  }

  it("keeps Approve shut until a buyer is chosen and the invoice is complete, then sends the terms", async () => {
    draw();
    const approve = await waitFor(() => screen.getByRole("button", { name: "Approve" }));
    expect((approve as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Price"), { target: { value: "90000" } });
    expect((approve as HTMLButtonElement).disabled).toBe(true);
    // choose the buyer through the picker
    answer = (m) => {
      if (m.includes("buyer_search")) return { ok: true, buyers: [{ name: "Samwel Njoroge", customer_name: "Samwel Njoroge", customer_type: "Individual", tax_id: null, mobile_no: null, payment_terms: null }] };
      if (m.includes("sale_terms")) return preview();
      if (m.includes("approve_cull")) return { ok: true, name: "ANI-DISP-1", status: "Approved" };
      return board;
    };
    fireEvent.click(screen.getByRole("button", { name: "Buyer" }));
    fireEvent.click(await screen.findByText("Samwel Njoroge"));
    await waitFor(() => expect((screen.getByRole("button", { name: "Approve" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(sent.some((c) => c.method.includes("approve_cull"))).toBe(true));
    const payload = sent.find((c) => c.method.includes("approve_cull"))!.args.payload as Record<string, unknown>;
    expect(payload).toMatchObject({ case: "ANI-DISP-1", customer: "Samwel Njoroge", sale_price: 90000, price_basis: "Per head" });
    expect(payload.buyer_name).toBeUndefined();
  });

  it("shows a vet, not a manager, no sale form at all", async () => {
    window.LIVESTOCK = { bootstrap: { user: "v@x.com", full_name: "V", roles: [], can: caps(false) } } as never;
    draw();
    await waitFor(() => screen.getByRole("button", { name: "Refuse" }));
    expect(screen.queryByLabelText("Buyer")).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });
});
