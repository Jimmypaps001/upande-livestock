import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useSaveShortcut } from "@/lib/use-save-shortcut";

/**
 * Ctrl+S saves, and never opens the browser's save dialog.
 *
 * The desk has trained everyone on this farm to press it. A page that answered
 * with "Save page as…" would be a page teaching them their work was not saved,
 * so the keystroke is swallowed whether or not this page has anything to do
 * with it — the lesser of the two surprises.
 */
function Harness({ onSave, enabled }: { onSave: () => void; enabled: boolean }) {
  useSaveShortcut(onSave, enabled);
  return <p>a page</p>;
}

function press(init: Partial<KeyboardEventInit> = {}) {
  const event = new KeyboardEvent("keydown", {
    key: "s",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
    ...init,
  });
  document.dispatchEvent(event);
  return event;
}

describe("Ctrl+S", () => {
  it("does what the save button does", () => {
    const save = vi.fn();
    render(<Harness onSave={save} enabled />);
    press();
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("works on a Mac too", () => {
    const save = vi.fn();
    render(<Harness onSave={save} enabled />);
    press({ ctrlKey: false, metaKey: true });
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("never lets the browser take it, even with nothing to save", () => {
    const save = vi.fn();
    render(<Harness onSave={save} enabled={false} />);
    const event = press();
    expect(event.defaultPrevented).toBe(true);
    expect(save).not.toHaveBeenCalled();
  });

  it("will not do what the button itself would refuse", () => {
    // Otherwise the keyboard is a way round a guard: the shortcut is disabled
    // by exactly the condition that disables the button.
    const save = vi.fn();
    render(<Harness onSave={save} enabled={false} />);
    press();
    expect(save).not.toHaveBeenCalled();
  });

  it("ignores a plain s, so typing a word does not save", () => {
    const save = vi.fn();
    render(<Harness onSave={save} enabled />);
    press({ ctrlKey: false });
    expect(save).not.toHaveBeenCalled();
  });

  it("calls the latest action, not the one bound on first render", () => {
    // Every page's save closes over its form state, so a stale closure would
    // post whatever was on screen when the page loaded.
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(<Harness onSave={first} enabled />);
    rerender(<Harness onSave={second} enabled />);
    press();
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("stops listening once the page is gone", () => {
    const save = vi.fn();
    const { unmount } = render(<Harness onSave={save} enabled />);
    unmount();
    press();
    expect(save).not.toHaveBeenCalled();
  });

  it("leaves the page alone otherwise", () => {
    render(<Harness onSave={() => {}} enabled />);
    expect(screen.getByText("a page")).toBeTruthy();
  });
});
