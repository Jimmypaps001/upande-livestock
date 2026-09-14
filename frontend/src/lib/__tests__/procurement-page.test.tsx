import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The procurement page, rendered and clicked.
 *
 * The behaviour worth a test: the order that leaves this page is the one the
 * operator kept, not the one the arithmetic proposed.
 */

const items = [
  {
    item_code: "4040010052",
    item_name: "High Phosphorous Mineral (Maziwa)",
    uom: "Kilogram",
    on_hand: 157,
    per_day: 30.155,
    days_cover: 5.2,
    runs_out_on: "2026-09-19",
    target_days: 28,
    order_qty: 688,
    source: "Raw material",
  },
  {
    item_code: "4040010029",
    item_name: "Limestone",
    uom: "Kilogram",
    on_hand: 147.24,
    per_day: 12.975,
    days_cover: 11.3,
    runs_out_on: "2026-09-25",
    target_days: 28,
    order_qty: 217,
    source: "Raw material",
  },
];

const payload = {
  ok: true,
  target_days: 28,
  items,
  warehouse: "Feed Store - Raw materials - KR",
  basis: "today's head counts and today's rations",
  open_requests: [],
};

const call = vi.fn(async (method?: string) =>
  (method || "").endsWith("create_feed_request")
    ? {
        ok: true,
        name: "MAT-MR-2026-1",
        warehouse: payload.warehouse,
        schedule_date: "2026-09-21",
        lines: 1,
        farm: "Kapkolia",
      }
    : payload,
);

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Procurement } = await import("@/pages/Procurement");

function draw() {
  return render(
    <TooltipProvider>
      <ToastProvider>
      <Procurement />
    </ToastProvider>
    </TooltipProvider>,
  );
}

describe("the procurement page", () => {
  beforeEach(() => call.mockClear());

  it("shows what is short and when it goes", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("Limestone")).toBeTruthy());
    expect(screen.getByText("2026-09-19")).toBeTruthy();
  });

  it("suggests a quantity that can be typed over", async () => {
    draw();
    const field = (await screen.findByLabelText(
      /Quantity of Limestone/,
    )) as HTMLInputElement;
    expect(field.value).toBe("217");
    fireEvent.change(field, { target: { value: "500" } });
    expect(field.value).toBe("500");
  });

  it("orders only the lines that were kept", async () => {
    // The store keeper dropping a line is the point of the screen: the farm
    // may be covering that feed another way, and the arithmetic cannot know.
    draw();
    await waitFor(() => expect(screen.getByText("Limestone")).toBeTruthy());
    fireEvent.click(screen.getAllByText("Drop")[0]);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Draft one request for 1 feed/ })).toBeTruthy(),
    );
  });

  it("says the request is drafted rather than sent", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("Limestone")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Draft one request/ }));
    await waitFor(() => expect(screen.getByText(/not submitted/)).toBeTruthy());
  });

  it("never offers a feed the farm mixes itself", async () => {
    // The server decides this; the page must not reintroduce one.
    draw();
    await waitFor(() => expect(screen.getByText("Limestone")).toBeTruthy());
    expect(screen.queryByText("Calves Meal")).toBeNull();
  });
});
