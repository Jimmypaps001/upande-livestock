import { describe, expect, it } from "vitest";
import { boundsOf, centroid, outlines, perHerd, placeLabel, type GeoJson, type Place, type Rotation } from "@/lib/paddocks";

const square = (w: number, s: number): GeoJson => ({
  type: "FeatureCollection",
  features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[w, s], [w + 2, s], [w + 2, s + 2], [w, s + 2], [w, s]]] } }],
});

const place = (o: Partial<Place>): Place => ({
  warehouse: "Paddock A1 - MUT", label: "Paddock A1", kind: "Paddock", area_ha: 0.14, geojson: square(0, 0),
  state: "occupied", heads: 98, head_per_ha: 700, herds: [{ herd: "Lactation Group 1", heads: 98, colour: "#2f7d4f" }],
  colour: "#2f7d4f", feed_kg: 0, ...o,
});

describe("paddock map helpers", () => {
  it("finds the middle of an outline, ignoring the repeated closing corner", () => {
    expect(centroid(square(10, 20))).toEqual([11, 21]);
    expect(centroid(null)).toBeNull();
    expect(centroid({ type: "FeatureCollection", features: [] })).toBeNull();
  });

  it("bounds every outline", () => {
    expect(boundsOf([{ geojson: square(0, 0) }, { geojson: square(10, 5) }, { geojson: null }])).toEqual([[0, 0], [12, 7]]);
    expect(boundsOf([{ geojson: null }])).toBeNull();
  });

  it("labels an occupied place with the herd and its head, a resting one as resting", () => {
    expect(placeLabel(place({}))).toEqual({ title: "Lactation Group 1", sub: "98 head" });
    expect(placeLabel(place({ state: "resting", herds: [], heads: 0, label: "Paddock A2" }))).toEqual({ title: "Paddock A2", sub: "Resting" });
    const two = place({ herds: [{ herd: "A", heads: 1, colour: "x" }, { herd: "B", heads: 2, colour: "y" }], heads: 3 });
    expect(placeLabel(two)).toEqual({ title: "A + B", sub: "3 head" });
  });

  it("builds one feature per ring carrying the colour and state", () => {
    const fc = outlines([place({}), place({ warehouse: "Paddock A2 - MUT", state: "resting", colour: "#9aa59a", geojson: null })]);
    expect(fc.features).toHaveLength(1);
    expect((fc.features[0] as { properties: { colour: string; state: string } }).properties).toMatchObject({ colour: "#2f7d4f", state: "occupied" });
  });

  it("states paddocks per herd to one place", () => {
    const r = { per_herd: 1.4 } as Rotation;
    expect(perHerd(r)).toBe("1.4");
    expect(perHerd({ per_herd: null } as Rotation)).toBe("—");
  });
});
