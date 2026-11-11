import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The calving screen asks birth_check the moment a cow is picked. A cow with
 * no confirmed pregnancy and no service in the window gets the explainer and
 * the retro path; a herdsman with backdating closed is told a manager must do
 * it, and cannot send it.
 */

const outside = {
  ok: true, allowed: false, basis: null, message: "no service", current_herd: "Lactating",
  dam: "COW-1", birth_date: "2026-11-01", window: { min_days: 270, max_days: 295 },
  service_from: "2026-01-10", service_to: "2026-02-04",
  retro_allowed: true, retro_refusal: "", is_manager: true, backdating_open: false, allow_diagnosis: true,
};

let answer: Record<string, unknown> = outside;

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  const m = method || "";
  void args;
  if (m.includes("posting_day")) return { ok: true, today: "2026-11-01", backdating_open: false };
  if (m.includes("event_options"))
    return {
      ok: true, animals: [], herds: [{ name: "Heifers", label: "Heifers" }], calving_outcomes: [],
      employee: "EMP-1", items_by_event: {},
      calving_animals: [{ name: "COW-1", label: "Daisy", herd: "Lactating", herd_label: "Lactating", repro: null }],
    };
  if (m.includes("calving_destinations")) return { error: "skip" };
  if (m.includes("birth_check")) return answer;
  if (m.includes("breeding_options"))
    return {
      ok: true, animals: [], diagnosis_animals: [], heat_animals: [], service_types: ["A.I.", "Natural"],
      diagnosis_results: [], sires: [], semen_items: [], default_semen_item: null, service_wait_days: 0,
      employee: "EMP-1",
      items_by_event: { Service: [{ value: "STRAW-1", label: "Chico · out of stock", item_name: "Chico",
        qty: 0, in_stock: false, warehouse: "Fridge", locations: [] }] },
    };
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Calving } = await import("@/pages/Calving");

function page() {
  return render(
    <TooltipProvider>
      <ToastProvider>
        <Calving />
      </ToastProvider>
    </TooltipProvider>,
  );
}

describe("calving: the birth window and the retro path", () => {
  beforeEach(() => {
    call.mockClear();
    answer = outside;
  });

  it("explains the window and offers the retro path, send held until it is filled", async () => {
    page();
    fireEvent.click(await screen.findByText("Daisy"));
    const panel = await screen.findByTestId("retro-birth");
    expect(panel.textContent).toMatch(/270–295 days/);
    expect(panel.textContent).toMatch(/The herd she was in on the service date/);
    expect(panel.textContent).toMatch(/pregnancy diagnosis \(optional\)/);
    expect(screen.getAllByTestId("backdated-badge").length).toBeGreaterThan(0);
    const send = screen.getByRole("button", { name: /Back-record the service and record the calving/ });
    expect(send).toHaveProperty("disabled", true);
    expect(screen.getByTestId("retro-problems").textContent).toMatch(/Give the service date/);
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith(
        expect.stringContaining("birth_check"),
        { payload: { dam: "COW-1", birth_date: "2026-11-01" } },
      ),
    );
  });

  it("a herdsman with backdating closed is told a manager must do it", async () => {
    answer = { ...outside, retro_allowed: false, is_manager: false,
      retro_refusal: "Ask a manager to record this birth, or to turn on Backdating Open." };
    page();
    fireEvent.click(await screen.findByText("Daisy"));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Ask a manager/);
    expect(screen.getByRole("button", { name: /Back-record the service/ })).toHaveProperty("disabled", true);
  });

  it("a dam with a service in the window records straight away", async () => {
    answer = { ...outside, allowed: true, basis: { kind: "service", service: "SERVICE-1", service_date: "2026-01-20" } };
    page();
    fireEvent.click(await screen.findByText("Daisy"));
    expect((await screen.findByTestId("birth-basis")).textContent).toMatch(/SERVICE-1/);
    expect(screen.queryByTestId("retro-birth")).toBeNull();
    expect(screen.getByRole("button", { name: /^Record the calving/ })).toHaveProperty("disabled", false);
  });
});
