import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EventFeed } from "@/components/animals/EventFeed";
import { lastServed } from "@/components/animals/AnimalPortrait";

describe("an animal's insemination on her page", () => {
  it("names the bull and the day she was last served", () => {
    expect(lastServed({ lastService: { on: "2026-11-17", sire: "STORMER", type: "A.I." } })).toBe(
      "STORMER · 2026-11-17",
    );
  });

  it("says the bull is not recorded rather than leaving it blank", () => {
    expect(lastServed({ lastService: { on: "2026-11-17", sire: null, type: "A.I." } })).toBe(
      "A.I., bull not recorded · 2026-11-17",
    );
  });

  it("is a dash only when she has never been served", () => {
    expect(lastServed({ lastService: null })).toBe("—");
    expect(lastServed({})).toBe("—");
  });

  it("marks an estimated date on the service and on the feed", () => {
    expect(lastServed({ lastService: { on: "2026-11-17", sire: "STORMER", type: "A.I.", estimated: true } })).toContain("(est.)");
    render(
      <EventFeed
        milestones={[
          { kind: "service", on: "2026-11-17", label: "Served", detail: "A.I. · by STORMER" },
          { kind: "drying", on: "2026-11-08", label: "Dried off", estimated: true },
        ]}
      />,
    );
    expect(screen.getByText("A.I. · by STORMER")).toBeTruthy();
    expect(screen.getAllByText("Estimated date")).toHaveLength(1);
  });
});
