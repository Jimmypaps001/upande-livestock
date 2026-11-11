import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnimalSearch } from "@/components/animals/AnimalSearch";
import { SilhouetteFrame } from "@/components/animals/AnimalSilhouette";
import type { AnimalSummary } from "@/lib/animals";
import {
  CALF_DAYS,
  HEIFER_DAYS,
  POSES,
  pickSilhouette,
  silhouetteClass,
  tagHash,
} from "@/lib/silhouettes";

const NOW = new Date("2026-11-11T00:00:00Z");
const born = (days: number) => new Date(NOW.getTime() - days * 86400000).toISOString().slice(0, 10);

describe("silhouetteClass", () => {
  it("sheep and goats by species, whatever else is known", () => {
    expect(silhouetteClass({ species: "Sheep", sex: "Male", stage: "bull" }, NOW)).toBe("sheep");
    expect(silhouetteClass({ species: "Goat", sex: "Female", bornOn: born(30) }, NOW)).toBe("goat");
  });

  it("a calf by stage, or by age under seven months", () => {
    expect(silhouetteClass({ sex: "Male", stage: "calf" }, NOW)).toBe("calf");
    expect(silhouetteClass({ sex: "Female", stage: "open", bornOn: born(CALF_DAYS - 1) }, NOW)).toBe("calf");
    expect(silhouetteClass({ sex: "Male", stage: "open", bornOn: born(CALF_DAYS) }, NOW)).toBe("steer");
  });

  it("a male is a steer unless he is a breeding bull", () => {
    expect(silhouetteClass({ sex: "Male", stage: "bull", bornOn: born(2000) }, NOW)).toBe("bull");
    for (const stage of ["weaner", "grower", "finisher", "market", "steer", "open", "retired"] as const) {
      expect(silhouetteClass({ sex: "Male", stage, bornOn: born(500) }, NOW)).toBe("steer");
    }
  });

  it("a female is a heifer until she has calved, or while young when the stage is not known", () => {
    expect(silhouetteClass({ sex: "Female", stage: "heifer", bornOn: born(1500) }, NOW)).toBe("heifer");
    expect(silhouetteClass({ sex: "Female", stage: "confirmed", bornOn: born(600) }, NOW)).toBe("cow");
    // the list sends "open" for everyone: age decides
    expect(silhouetteClass({ sex: "Female", stage: "open", bornOn: born(HEIFER_DAYS - 1) }, NOW)).toBe("heifer");
    expect(silhouetteClass({ sex: "Female", stage: "open", bornOn: born(HEIFER_DAYS) }, NOW)).toBe("cow");
    expect(silhouetteClass({ sex: "Female", stage: "open" }, NOW)).toBe("cow");
  });

  it("sex not recorded is drawn as the feedlot's steer", () => {
    expect(silhouetteClass({ sex: null, stage: "unknown", bornOn: born(400) }, NOW)).toBe("steer");
  });
});

describe("pickSilhouette", () => {
  it("is stable for an animal and stays inside its class", () => {
    const a = { id: "A048/19", sex: "Female", stage: "open" as const, bornOn: born(2600) };
    const first = pickSilhouette(a, NOW);
    expect(POSES.cow).toContain(first);
    for (let i = 0; i < 5; i++) expect(pickSilhouette(a, NOW)).toBe(first);
    // the number is read the way the farm writes it
    expect(pickSilhouette({ ...a, id: " a048/19 " }, NOW)).toBe(first);
  });

  it("spreads a herd of photo-less animals over every pose of the class", () => {
    const seen = new Set<string>();
    for (let n = 1; n <= 60; n++) {
      const id = `B${String(n).padStart(3, "0")}/24`;
      seen.add(pickSilhouette({ id, sex: "Male", stage: "finisher", bornOn: born(500) }, NOW));
    }
    expect([...seen].sort()).toEqual([...POSES.steer].sort());
  });

  it("a breeding bull has the one pose", () => {
    expect(pickSilhouette({ id: "B001/19", sex: "Male", stage: "bull" }, NOW)).toBe("bull");
  });

  it("hashes to an unsigned 32-bit number", () => {
    const h = tagHash("A001/20");
    expect(Number.isInteger(h)).toBe(true);
    expect(h).toBeGreaterThanOrEqual(0);
    expect(h).toBeLessThan(2 ** 32);
    expect(tagHash("")).toBe(tagHash("   "));
  });
});

describe("the drawings", () => {
  it("has a file for every pose, drawn in the current colour", () => {
    const names = Object.values(POSES).flat();
    for (const name of names) {
      const id = findIdFor(name);
      const { container } = render(<SilhouetteFrame animal={id} />);
      const svg = container.querySelector("svg")!;
      expect(svg.getAttribute("data-pose")).toBe(name);
      expect(svg.innerHTML).toContain("currentColor");
      expect(svg.querySelectorAll("path").length).toBeGreaterThan(0);
    }
  });

  it("sheep and goats, with no artwork of their own yet, wear the calf's", () => {
    expect(POSES.sheep).toEqual(POSES.calf);
    expect(POSES.goat).toEqual(POSES.calf);
  });
  it("a photo-less row in the animal search wears its silhouette", () => {
    const a: AnimalSummary = {
      id: "B013/26", name: "B013/26", sex: "Male", herd: "Finishers", breed: "Boran",
      bornOn: "2024-01-01", status: "Active", stage: "open", photo: null, thumb: null,
    };
    const { container } = render(<AnimalSearch animals={[a]} selectedId={null} onSelect={() => {}} />);
    const svg = container.querySelector("svg[data-pose]");
    expect(svg?.getAttribute("data-kind")).toBe("steer");
    expect(container.querySelectorAll("img")).toHaveLength(0);
  });
});

/** An animal whose pick is `name`, found by trying numbers in its class. */
function findIdFor(name: string) {
  const base = name.startsWith("calf")
        ? { sex: "Male", stage: "calf" as const }
        : name.startsWith("bull")
          ? { sex: "Male", stage: "bull" as const }
          : name.startsWith("steer")
            ? { sex: "Male", stage: "finisher" as const }
            : name.startsWith("heifer")
              ? { sex: "Female", stage: "heifer" as const }
              : { sex: "Female", stage: "confirmed" as const };
  for (let n = 0; n < 500; n++) {
    const a = { id: `T${n}`, ...base };
    if (pickSilhouette(a) === name) return a;
  }
  throw new Error(`no number picks ${name}`);
}
