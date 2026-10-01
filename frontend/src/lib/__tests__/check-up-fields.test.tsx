import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The vet's reasoning, which the form threw away.
 *
 * `create_check_up` sets `doc.differential_notes` on the Livestock Diagnosis —
 * a real Small Text field labelled "Differential / Notes" — and every one of
 * its neighbours is on the form: Suspected (`suggested_disease`), What was done
 * (`action_taken`), Notes (`action_notes`), Look again on (`follow_up_date`).
 * Only this one was never rendered, so the differential — what else it might
 * be, and why — had nowhere to go on the screen a vet actually uses.
 *
 * Found by sweeping every endpoint's payload keys against the frontend source;
 * it is the same shape of gap as `semen_qty`.
 */

const options = {
  ok: true,
  animals: [
    { name: "A039/26", label: "APIJA (A039/26)", herd: "Lactating group 1", herd_label: "Lactating group 1", repro: "Open" },
  ],
  diseases: ["Mastitis", "Milk fever"],
  actions: ["Treated", "Watch"],
  appearances: ["Bright", "Dull"],
  hydrations: ["Normal", "Dehydrated"],
  severities: ["Mild"],
  drug_items: [],
  warehouses: [],
  employee: "HR-EMP-001" as string | null,
};

const sent: Record<string, unknown>[] = [];
const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  if ((method || "").includes("create_check_up")) {
    sent.push(args ?? {});
    return { ok: true, name: "DIAG-2026-0001" };
  }
  return options;
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { CheckUp } = await import("@/pages/Health");

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <CheckUp />
      </ToastProvider>
    </TooltipProvider>,
  );

describe("the check-up form", () => {
  beforeEach(() => {
    call.mockClear();
    sent.length = 0;
  });

  it("offers somewhere to write the differential", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("APIJA (A039/26)")).toBeTruthy());
    fireEvent.click(screen.getByText("APIJA (A039/26)"));
    expect(screen.getByLabelText("Differential / notes")).toBeTruthy();
  });

  it("sends the differential to the server", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("APIJA (A039/26)")).toBeTruthy());
    fireEvent.click(screen.getByText("APIJA (A039/26)"));
    fireEvent.change(screen.getByLabelText("Why she was looked at"), {
      target: { value: "Off her feed" },
    });
    fireEvent.change(screen.getByLabelText("Differential / notes"), {
      target: { value: "Could be ketosis; check urine." },
    });
    const button = screen.getByRole("button", { name: /Record the check up/ });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(sent.length).toBe(1));
    expect((sent[0].payload as Record<string, unknown>).differential_notes).toBe(
      "Could be ketosis; check urine.",
    );
  });
});
