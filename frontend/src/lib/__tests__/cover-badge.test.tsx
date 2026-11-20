import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CoverBadge } from "@/components/animals/CoverBadge";
import { coverLabel } from "@/lib/animals";

describe("the insurance cover badge", () => {
  it("says Insured, expiring and expired in the farm's words", () => {
    expect(coverLabel("insured")).toBe("Insured");
    expect(coverLabel("expiring")).toBe("Cover expiring");
    expect(coverLabel("expired")).toBe("Cover expired");
  });

  it("names no cover only on the profile, never in the list", () => {
    expect(coverLabel("none")).toBeNull();
    expect(coverLabel("none", true)).toBe("No cover");
  });

  it("draws nothing for an animal with no asset or a site with no insurance module", () => {
    const { container } = render(
      <>
        <CoverBadge state="no_asset" detail />
        <CoverBadge state="unavailable" detail />
        <CoverBadge state={undefined} />
      </>,
    );
    expect(container.textContent).toBe("");
  });

  it("carries the policy on hover", () => {
    render(
      <CoverBadge
        state="insured"
        info={{ state: "insured", policy: "P1", policyNumber: "N-9", insurer: "Jubilee",
                sumInsured: 1, start: "2026-01-01", end: "2026-12-31", daysLeft: 40 }}
      />,
    );
    const b = screen.getByTestId("cover-badge");
    expect(b.getAttribute("title")).toContain("Jubilee");
    expect(b.textContent).toBe("Insured");
  });
});
