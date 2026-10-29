import { call, type Envelope } from "@/lib/frappe";

/** Paddock and pen outlines coloured by herd, plus the rotation check. Shapes follow
 *  `serverscripts/projection/get_paddock_map`. */

const PATH = "upande_livestock.serverscripts.projection.get_paddock_map.get_paddock_map";

export type GeoJson = {
  type: string;
  features?: Array<{ type: string; properties?: Record<string, unknown>; geometry: { type: string; coordinates: unknown } | null }>;
  geometry?: { type: string; coordinates: unknown } | null;
};

export type PlaceHerd = { herd: string; heads: number; colour: string };

export type Place = {
  warehouse: string;
  label: string;
  kind: "Paddock" | "Pen";
  area_ha: number | null;
  geojson: GeoJson | null;
  state: "occupied" | "resting";
  heads: number;
  head_per_ha: number | null;
  herds: PlaceHerd[];
  colour: string;
  feed_kg: number;
};

export type Rotation = {
  paddocks: number;
  grazing_herds: number;
  per_herd: number | null;
  needed_per_herd: number;
  needed_total: number;
  shortfall: number;
  rest_days: number | null;
  target_rest_days: number;
  graze_days: number;
  enough: boolean;
  message: string;
  grazing_ha: number;
  grazing_head: number;
  head_per_ha: number | null;
};

export type PaddockMapData = {
  places: Place[];
  herds: Array<{ herd: string; herd_class: string; paddock: string | null; heads: number; colour: string | null; grazing: boolean }>;
  unplaced: string[];
  rotation: Rotation;
  resting: string[];
};

export function getPaddockMap(): Promise<Envelope<PaddockMapData>> {
  return call(PATH, {});
}

export const RESTING_COLOUR = "#9aa59a";

type Ring = number[][];

function rings(g: GeoJson | null): Ring[] {
  if (!g) return [];
  const geoms = g.features ? g.features.map((f) => f.geometry) : [g.geometry ?? null];
  const out: Ring[] = [];
  for (const geom of geoms) {
    if (!geom) continue;
    if (geom.type === "Polygon") out.push((geom.coordinates as Ring[])[0]);
    else if (geom.type === "MultiPolygon") for (const p of geom.coordinates as Ring[][]) out.push(p[0]);
  }
  return out.filter((r) => r && r.length > 0);
}

/** The middle of a place's outline as [lng, lat] (mean of the corners), or null without one. */
export function centroid(g: GeoJson | null): [number, number] | null {
  const pts = rings(g).flatMap((r) => (r.length > 1 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1] ? r.slice(0, -1) : r));
  if (!pts.length) return null;
  return [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length];
}

/** [[west, south], [east, north]] around every outline, or null when none has one. */
export function boundsOf(places: Array<{ geojson: GeoJson | null }>): [[number, number], [number, number]] | null {
  const pts = places.flatMap((p) => rings(p.geojson).flat());
  if (!pts.length) return null;
  const lngs = pts.map((p) => p[0]);
  const lats = pts.map((p) => p[1]);
  return [
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ];
}

/** The label drawn on a place: the herd(s) and the head standing there, or "Resting". */
export function placeLabel(p: Pick<Place, "label" | "state" | "herds" | "heads">): { title: string; sub: string } {
  if (p.state === "resting" || p.herds.length === 0) return { title: p.label, sub: "Resting" };
  const names = p.herds.map((h) => h.herd).join(" + ");
  return { title: names, sub: `${p.heads} head` };
}

/** One FeatureCollection of every outline carrying its colour, kind and state, for a single map source. */
export function outlines(places: Place[]) {
  const features: unknown[] = [];
  for (const p of places) {
    for (const r of rings(p.geojson)) {
      features.push({
        type: "Feature",
        properties: { name: p.warehouse, label: p.label, colour: p.colour, state: p.state, kind: p.kind },
        geometry: { type: "Polygon", coordinates: [r] },
      });
    }
  }
  return { type: "FeatureCollection" as const, features };
}

/** Paddocks per grazing herd to one place, as the page states it ("1.4"). */
export function perHerd(r: Rotation): string {
  return r.per_herd === null ? "—" : r.per_herd.toFixed(1);
}
