import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Notice, plainText } from "@/components/feeding/Notice";

/**
 * The server's words, made readable without being made dangerous.
 *
 * Frappe's `frappe.throw` takes HTML and this app uses it — the calving guard
 * answers with headings and numbered steps in markup. A herdsman must not be
 * shown the tags, and must not be shown rendered HTML either: some of these
 * strings carry text a person typed.
 */
describe("the server's message, as a person reads it", () => {
  it("turns the app's own calving refusal into something legible", () => {
    const real =
      '<b><img src="/assets/upande_livestock/icons/warning.svg" width="15" />' +
      "No active pregnancy to calve from</b><br><br>This animal has no confirmed " +
      "pregnancy to calve from.<br><br><b>Action Required:</b><br>1. Ensure a " +
      "service has been recorded<br>2. Pregnancy must be confirmed via diagnosis";
    const out = plainText(real) as string;
    expect(out).not.toContain("<b>");
    expect(out).not.toContain("<br>");
    expect(out).toContain("No active pregnancy to calve from");
    // The icon in front of the heading is markup like any other: stripped,
    // never rendered, and never left in as a tag a herdsman has to read past.
    expect(out).not.toContain("<img");
    expect(out).not.toContain("assets/upande_livestock");
    expect(out).toContain("1. Ensure a service has been recorded");
    // The breaks it meant survive as breaks.
    expect(out.split("\n").length).toBeGreaterThan(3);
  });

  it("leaves a plain message exactly as it arrived", () => {
    // The backdated-feed refusal names items and dates and must not be touched.
    const plain = "Short of 4040010082 on 2026-09-01.\n\nEarliest workable date: 2026-09-03.";
    expect(plainText(plain)).toBe(plain);
  });

  it("never renders markup as markup", () => {
    render(<Notice tone="error">{"<img src=x onerror=alert(1)>Beatrice is sick"}</Notice>);
    expect(screen.getByRole("alert").querySelector("img")).toBeNull();
    expect(screen.getByRole("alert").textContent).toContain("Beatrice is sick");
  });

  it("passes a React child through untouched", () => {
    render(
      <Notice tone="info">
        <span data-testid="child">built by a page</span>
      </Notice>,
    );
    expect(screen.getByTestId("child")).toBeTruthy();
  });
});
