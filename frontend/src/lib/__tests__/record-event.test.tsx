import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The scaffold the twelve record-an-event screens share, and the two
 * promises it makes.
 *
 * THE ANIMAL LIST IS THE SERVER'S. Each options endpoint already narrows —
 * a weaner is not offered for service, a cow with no open service is not
 * offered for diagnosis — and the screen must not re-decide that, because two
 * answers to "who may be served" drift apart the first time one is changed.
 *
 * And a REQUIRED FIELD BLOCKS THE SUBMIT rather than letting the server refuse
 * it, so a herdsman standing in a pen is told what is missing before the
 * round trip.
 */

const breeding = {
  ok: true,
  animals: [
    { name: "A039/26", label: "APIJA (A039/26)", herd: "Lactating group 1", herd_label: "Lactating group 1", repro: "Open" },
  ],
  diagnosis_animals: [
    { name: "A101/23", label: "SITA (A101/23)", herd: "Lactating group 2", herd_label: "Lactating group 2", repro: "Served" },
  ],
  service_types: ["A.I.", "Natural"],
  diagnosis_results: ["Confirmed", "Not Pregnant"],
  sires: ["BULL-1"],
  semen_items: [{ item_code: "SEMEN-1" }],
  default_semen_item: "SEMEN-1",
  service_wait_days: 60,
  employee: "HR-EMP-001" as string | null,
};

const call = vi.fn(async (method?: string) =>
  (method || "").includes("create_service_event")
    ? { ok: true, name: "SERVICE-2026-0001" }
    : breeding,
);

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Service, Diagnosis } = await import("@/pages/Breeding");

const draw = (Page: () => React.ReactElement) =>
  render(
    <TooltipProvider>
      <ToastProvider>
      <Page />
    </ToastProvider>
    </TooltipProvider>,
  );

describe("the record-an-event scaffold", () => {
  beforeEach(() => call.mockClear());

  it("offers the animals the server said may be served", async () => {
    draw(Service);
    await waitFor(() => expect(screen.getByText("APIJA (A039/26)")).toBeTruthy());
    expect(screen.getByText("1 offered")).toBeTruthy();
  });

  it("offers a different list for a diagnosis than for a service", async () => {
    // Servable and diagnosable are different questions, and the server answers
    // them separately. A screen that used one list for both would invite a
    // "Confirmed" for a cow nobody served.
    draw(Diagnosis);
    await waitFor(() => expect(screen.getByText("SITA (A101/23)")).toBeTruthy());
    expect(screen.queryByText("APIJA (A039/26)")).toBeNull();
  });

  it("says nothing is selected until something is", async () => {
    draw(Service);
    await waitFor(() => expect(screen.getByText("Nothing selected")).toBeTruthy());
  });

  it("holds the submit until a required field is answered, and says which", async () => {
    draw(Service);
    await waitFor(() => expect(screen.getByText("APIJA (A039/26)")).toBeTruthy());
    fireEvent.click(screen.getByText("APIJA (A039/26)"));
    const button = await screen.findByRole("button", { name: /Record the service/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Still needs how/i)).toBeTruthy();
  });

  it("records once the answer is there, and says what happened", async () => {
    draw(Service);
    await waitFor(() => expect(screen.getByText("APIJA (A039/26)")).toBeTruthy());
    fireEvent.click(screen.getByText("APIJA (A039/26)"));
    fireEvent.change(await screen.findByLabelText("How"), { target: { value: "A.I." } });
    // The fixture's options carry an Employee, so nothing is asked for here.
    const button = screen.getByRole("button", { name: /Record the service/ });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText(/SERVICE-2026-0001/)).toBeTruthy());
  });

  it("asks who is recording when the login has no Employee linked", async () => {
    // The server refuses an event that does not say who made it. Asked for on
    // the screen rather than discovered on submit, standing in a pen.
    call.mockImplementation(async (method?: string) =>
      (method || "").includes("create_")
        ? { ok: true, name: "X" }
        : { ...breeding, employee: null },
    );
    draw(Service);
    await waitFor(() => expect(screen.getByText("APIJA (A039/26)")).toBeTruthy());
    fireEvent.click(screen.getByText("APIJA (A039/26)"));
    await screen.findByLabelText("Who is recording this");
    fireEvent.change(screen.getByLabelText("How"), { target: { value: "A.I." } });
    expect(
      (screen.getByRole("button", { name: /Record the service/ }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("does not render a select the farm has no options for", async () => {
    // An empty dropdown is a field that looks broken. The server decides what
    // exists; a screen offering "—" and nothing else is worse than no field.
    call.mockImplementation(async (method?: string) =>
      (method || "").includes("create_") ? { ok: true, name: "X" } : { ...breeding, sires: [] },
    );
    draw(Service);
    await waitFor(() => expect(screen.getByText("APIJA (A039/26)")).toBeTruthy());
    fireEvent.click(screen.getByText("APIJA (A039/26)"));
    await screen.findByLabelText("How");
    expect(screen.queryByLabelText("Sire")).toBeNull();
  });
});
