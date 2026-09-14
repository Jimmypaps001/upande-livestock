import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Who is recording this, and the two bugs that were in the way.
 *
 * The field asking for an operator UNMOUNTED on the first keystroke, because
 * "do we need to ask" was written as "is the box empty". And it was a free-text
 * box in front of a link field, so typing "d" and saving came back "Could not
 * find Operator(technician): d".
 */

const call = vi.fn(async () => ({
  ok: true,
  mine: null,
  query: "",
  more: false,
  employees: [
    { value: "HR-EMP-1", label: "JOSIAH KIPTOO", detail: "HR-EMP-1 · Herdsman" },
    { value: "HR-EMP-2", label: "MARY CHEPKOECH", detail: "HR-EMP-2 · Milker" },
  ],
}));

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

// Imported AFTER the mock, not above it: `vi.mock` is hoisted to the top of the
// file, so a static import runs the factory before `call` exists and the whole
// file fails to load with "Cannot access 'call' before initialization".
const { OperatorField } = await import("@/components/events/OperatorField");
const { PageDock } = await import("@/components/PageDock");

describe("naming the operator", () => {
  beforeEach(() => call.mockClear());

  it("stays on screen while somebody types into it", async () => {
    // It disappeared on the first letter, which read as the page breaking.
    const onChange = vi.fn();
    render(<OperatorField operator="" onChange={onChange} />);
    const field = screen.getByLabelText("Who is recording this");
    fireEvent.change(field, { target: { value: "jos" } });
    await waitFor(() => expect(screen.getByLabelText("Who is recording this")).toBeTruthy());
  });

  it("offers the people who match what was typed", async () => {
    render(<OperatorField operator="" onChange={vi.fn()} />);
    fireEvent.focus(screen.getByLabelText("Who is recording this"));
    await waitFor(() => expect(screen.getByText("JOSIAH KIPTOO")).toBeTruthy());
    expect(screen.getByText("HR-EMP-1 · Herdsman")).toBeTruthy();
  });

  it("sends an employee, never the half-typed text", async () => {
    // "d" was reaching the server as an Employee and being refused there.
    const onChange = vi.fn();
    render(<OperatorField operator="" onChange={onChange} />);
    const field = screen.getByLabelText("Who is recording this");
    fireEvent.change(field, { target: { value: "d" } });
    await waitFor(() => expect(screen.getByText("JOSIAH KIPTOO")).toBeTruthy());
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("JOSIAH KIPTOO"));
    expect(onChange).toHaveBeenCalledWith("HR-EMP-1");
  });

  it("searches once for a burst of typing, not once per key", async () => {
    render(<OperatorField operator="" onChange={vi.fn()} />);
    const field = screen.getByLabelText("Who is recording this");
    fireEvent.focus(field);
    for (const t of ["j", "jo", "jos", "josi"]) {
      fireEvent.change(field, { target: { value: t } });
    }
    await waitFor(() => expect(screen.getByText("JOSIAH KIPTOO")).toBeTruthy());
    expect(call.mock.calls.length).toBeLessThanOrEqual(2);
  });
});

describe("the dock pill", () => {
  it("does not say the page's name twice", () => {
    // "Animals  UPANDE LIVESTOCK · ANIMALS" was the page name three times.
    render(<PageDock eyebrow="Upande Livestock · Animals" title="Animals" progress={1} />);
    expect(screen.queryByText(/Upande Livestock · Animals/)).toBeNull();
    expect(screen.getByText("Animals")).toBeTruthy();
  });

  it("keeps the section when it actually adds something", () => {
    render(<PageDock eyebrow="Upande Livestock · Breeding" title="Service" progress={1} />);
    expect(screen.getByText("Breeding")).toBeTruthy();
    expect(screen.getByText("Service")).toBeTruthy();
  });
});
