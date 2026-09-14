import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "@/components/Toast";

/**
 * What just happened, said without moving the page.
 *
 * An inline notice pushed every card down the moment a button answered, so the
 * control you had just clicked jumped out from under the pointer — and on a
 * scrolled page the answer appeared somewhere you were not looking. That is the
 * bug these replace, so the test that matters is that they do not take part in
 * the layout at all.
 */

function Harness({ tone, text }: { tone?: "ok" | "error" | "info"; text: string }) {
  const toast = useToast();
  return (
    <div>
      <p>the page</p>
      <button type="button" onClick={() => toast(text, tone)}>
        do it
      </button>
    </div>
  );
}

const draw = (props: { tone?: "ok" | "error" | "info"; text: string }) =>
  render(
    <ToastProvider>
      <Harness {...props} />
    </ToastProvider>,
  );

describe("saying what happened", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("floats rather than sitting in the page", async () => {
    draw({ text: "2 animals moved into 2-4." });
    fireEvent.click(screen.getByText("do it"));
    const toast = await screen.findByRole("status");
    // Fixed: it is out of flow, so nothing below it moves when it appears.
    const layer = toast.parentElement as HTMLElement;
    expect(layer.className).toContain("fixed");
    expect(layer.className).toContain("z-50");
  });

  it("a confirmation goes on its own", async () => {
    draw({ text: "Saved." });
    fireEvent.click(screen.getByText("do it"));
    await screen.findByRole("status");
    act(() => vi.advanceTimersByTime(6000));
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  });

  it("a refusal stays until it is dismissed", async () => {
    // The farm's refusals carry instructions — which feeds are short, the
    // earliest date that would work. One must not vanish mid-sentence.
    draw({ tone: "error", text: "Short of silage on 2026-09-01." });
    fireEvent.click(screen.getByText("do it"));
    await screen.findByRole("alert");
    act(() => vi.advanceTimersByTime(60_000));
    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Dismiss"));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("interrupts for a refusal and waits its turn for a confirmation", async () => {
    // `alert` is announced at once; `status` waits for a pause. A refusal the
    // operator has to act on earns the interruption; "saved" does not.
    const { unmount } = draw({ tone: "error", text: "No." });
    fireEvent.click(screen.getByText("do it"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    unmount();
    draw({ tone: "ok", text: "Yes." });
    fireEvent.click(screen.getByText("do it"));
    expect(await screen.findByRole("status")).toBeTruthy();
  });

  it("keeps the server's words but not its markup", async () => {
    draw({ tone: "error", text: "<b>No Active Pregnancy Found!</b><br>Record a service." });
    fireEvent.click(screen.getByText("do it"));
    const toast = await screen.findByRole("alert");
    expect(toast.textContent).toContain("No Active Pregnancy Found!");
    expect(toast.textContent).not.toContain("<b>");
    expect(toast.querySelector("b")).toBeNull();
  });

  it("shows no more than three at once", async () => {
    // A stack taller than that is one nobody reads.
    draw({ text: "again" });
    for (let i = 0; i < 5; i++) fireEvent.click(screen.getByText("do it"));
    await waitFor(() => expect(screen.getAllByRole("status").length).toBe(3));
  });

  it("says nothing when there is nothing to say", async () => {
    draw({ text: "   " });
    fireEvent.click(screen.getByText("do it"));
    expect(screen.queryByRole("status")).toBeNull();
  });
});
