import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Three ways a farm weighs, and the screen has to offer all three.
 *
 * A row per animal is only one of them. A pen walks onto a platform and the
 * platform reads one figure; six heifers that plainly match get one figure
 * between them. Both were impossible here, so both were done on paper.
 */

const payloads: Record<string, unknown> = {
  weight_options: {
    ok: true,
    animals: [
      { name: "A001/22", label: "A001/22", herd: "0-2", herd_label: "0-2", repro: null },
      { name: "A002/22", label: "A002/22", herd: "0-2", herd_label: "0-2", repro: null },
    ],
    herds: [{ name: "0-2", label: "0-2", heads: 2 }],
    methods: ["Platform Scale", "Visual Estimate"],
    employee: "HR-EMP-00001",
  },
  record_weights: { ok: true, count: 2, recorded: [], skipped: [], failed: [] },
};

const call = vi.fn(async (method?: string, args?: Record<string, unknown>) => {
  void args;
  const key = Object.keys(payloads)
    .filter((k) => (method || "").includes(k))
    .sort((a, b) => b.length - a.length)[0];
  return key ? payloads[key] : { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Weights } = await import("@/pages/Weights");

const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <Weights />
      </ToastProvider>
    </TooltipProvider>,
  );

async function pickBoth() {
  draw();
  await waitFor(() => expect(screen.getByText("Select all 2 shown")).toBeTruthy());
  fireEvent.click(screen.getByText("Select all 2 shown"));
}

describe("the weighing screen", () => {
  it("offers all three ways a farm weighs", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("One at a time")).toBeTruthy());
    expect(screen.getByText("A pen on the platform")).toBeTruthy();
    expect(screen.getByText("One weight for animals of a size")).toBeTruthy();
  });

  it("divides a platform total by the head on it, before anything is sent", async () => {
    await pickBoth();
    fireEvent.click(screen.getByText("A pen on the platform"));
    const box = await waitFor(() => screen.getByLabelText(/Total on the platform/));
    fireEvent.change(box, { target: { value: "500" } });
    // The arithmetic is shown while it can still be called wrong.
    await waitFor(() =>
      expect(screen.getByText(/500.*over 2 head.*250.*each/)).toBeTruthy(),
    );
  });

  it("sends the group rather than a row per animal", async () => {
    await pickBoth();
    fireEvent.click(screen.getByText("A pen on the platform"));
    const box = await waitFor(() => screen.getByLabelText(/Total on the platform/));
    fireEvent.change(box, { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: /Record 2 weights/ }));
    await waitFor(() =>
      expect(call.mock.calls.some((c) => String(c[0]).includes("record_weights"))).toBe(true),
    );
    const sent = call.mock.calls.find((c) => String(c[0]).includes("record_weights"));
    const payload = (sent?.[1] as { payload: Record<string, unknown> }).payload;
    expect((payload.group as { total_weight_kg: number }).total_weight_kg).toBe(500);
    expect(payload.weights).toEqual([]);
  });

  it("says a copied figure is an estimate before it is recorded", async () => {
    await pickBoth();
    fireEvent.click(screen.getByText("One weight for animals of a size"));
    const box = await waitFor(() => screen.getByLabelText(/Weight each/));
    fireEvent.change(box, { target: { value: "310" } });
    await waitFor(() =>
      expect(screen.getByText(/recorded against all 2, as an estimate/)).toBeTruthy(),
    );
  });
});
