import { describe, expect, it } from "vitest";
import catalog from "@/lib/event-catalog.json";
import {
  EVENT_CATALOG, EVENT_GROUPS, eventIcon, iconByName, sortEventTypes, viewEntry,
} from "@/lib/event-icons";

const keys = EVENT_CATALOG.map((e) => e.key);

describe("event catalog", () => {
  it("opens with servicing, then health, then quality, in the agreed order", () => {
    expect(keys.slice(0, 10)).toEqual([
      "Heat Detection", "Service", "Pregnancy Diagnosis", "Abortion", "Calving", "Birth",
      "Check Up", "Health Case", "Treatment", "Milk Quality",
    ]);
  });
  it("groups contiguously and every group is declared", () => {
    const seen: string[] = [];
    for (const e of EVENT_CATALOG) if (seen[seen.length - 1] !== e.group) seen.push(e.group);
    expect(seen).toEqual(EVENT_GROUPS.map((g) => g.key));
    expect(EVENT_CATALOG.slice(0, 6).every((e) => e.group === "servicing")).toBe(true);
    expect(EVENT_CATALOG.slice(6, 9).every((e) => e.group === "health")).toBe(true);
  });
  it("gives each event one icon, distinct, and every icon resolves", () => {
    const icons = EVENT_CATALOG.map((e) => e.icon);
    expect(new Set(icons).size).toBe(icons.length);
    for (const e of EVENT_CATALOG) expect(iconByName(e.icon)).toBeDefined();
    expect(new Set(keys).size).toBe(keys.length);
    expect(eventIcon("Heat Detection")).toBe(iconByName("Flame"));
    expect(eventIcon("Nonsense")).toBe(iconByName("Sparkles"));
  });
  it("sorts event types into catalog order, unknown last", () => {
    expect(sortEventTypes(["Treatment", "Zed", "Service", "Heat Detection"])).toEqual([
      "Heat Detection", "Service", "Treatment", "Zed",
    ]);
  });
  it("maps desk views and the JSON mirrors the module", () => {
    expect(viewEntry("diagnosis")?.eventType).toBe("Pregnancy Diagnosis");
    expect(viewEntry("husbandry")?.group).toBe("husbandry");
    expect(catalog.events.length).toBe(EVENT_CATALOG.length);
  });
});
