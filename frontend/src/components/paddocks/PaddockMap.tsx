import { useEffect, useRef, useState } from "react";
import maplibregl, { type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { boundsOf, centroid, outlines, placeLabel, type Place } from "@/lib/paddocks";
import { cn } from "@/lib/utils";

/**
 * Paddock and pen outlines on a satellite (or street) base map, each filled with its herd's colour and
 * labelled with the herd name and head. A resting paddock is drawn grey and labelled "Resting".
 *
 * Labels are map markers (HTML), not a symbol layer: a symbol layer needs a glyph server and this map has
 * none. `selected` highlights one outline; clicking an outline reports its warehouse.
 */
type Basemap = "satellite" | "street";

const SOURCE = "places";
const FILL = "places-fill";
const LINE = "places-line";
const SELECTED = "places-selected";

function style(initial: Basemap): StyleSpecification {
  return {
    version: 8,
    sources: {
      satellite: {
        type: "raster",
        tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        tileSize: 256,
        maxzoom: 19,
      },
      street: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19 },
    },
    layers: [
      { id: "street", type: "raster", source: "street", layout: { visibility: initial === "street" ? "visible" : "none" } },
      { id: "satellite", type: "raster", source: "satellite", layout: { visibility: initial === "satellite" ? "visible" : "none" } },
    ],
  };
}

function labelEl(p: Place): HTMLElement {
  const { title, sub } = placeLabel(p);
  const el = document.createElement("div");
  el.className = "paddock-label";
  el.dataset.place = p.warehouse;
  el.style.cssText =
    "pointer-events:none;text-align:center;font:600 11px/1.25 Poppins,system-ui,sans-serif;color:#111;" +
    "background:rgba(255,255,255,.88);padding:2px 6px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.25);white-space:nowrap";
  const a = document.createElement("div");
  a.textContent = title;
  const b = document.createElement("div");
  b.textContent = sub;
  b.style.cssText = "font-weight:500;color:#555";
  el.append(a, b);
  return el;
}

export function PaddockMap({
  places,
  selected,
  onSelect,
  className,
}: {
  places: Place[];
  selected?: string | null;
  onSelect?: (warehouse: string) => void;
  className?: string;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const latest = useRef({ places, onSelect });
  latest.current = { places, onSelect };
  const [ready, setReady] = useState(false);
  const [base, setBase] = useState<Basemap>("satellite");

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const bounds = boundsOf(latest.current.places);
    const map = new maplibregl.Map({
      container: el,
      style: style("satellite"),
      center: bounds ? [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2] : [36.75, 0.06],
      zoom: 17,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    map.once("load", () => {
      map.addSource(SOURCE, { type: "geojson", data: outlines(latest.current.places) as never });
      map.addLayer({ id: FILL, type: "fill", source: SOURCE, paint: { "fill-color": ["get", "colour"], "fill-opacity": ["case", ["==", ["get", "state"], "resting"], 0.35, 0.65] } });
      map.addLayer({ id: LINE, type: "line", source: SOURCE, paint: { "line-color": "#ffffff", "line-width": 1.5 } });
      map.addLayer({ id: SELECTED, type: "line", source: SOURCE, filter: ["==", ["get", "name"], ""], paint: { "line-color": "#0a0a0a", "line-width": 3 } });
      map.on("click", FILL, (e) => {
        const name = e.features?.[0]?.properties?.name as string | undefined;
        if (name) latest.current.onSelect?.(name);
      });
      map.on("mouseenter", FILL, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", FILL, () => (map.getCanvas().style.cursor = ""));
      if (bounds) map.fitBounds(bounds, { padding: 40, maxZoom: 20, duration: 0 });
      setReady(true);
    });
    return () => {
      markers.current.forEach((m) => m.remove());
      markers.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Refill the outlines and the labels whenever the places change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource(SOURCE) as maplibregl.GeoJSONSource | undefined)?.setData(outlines(places) as never);
    markers.current.forEach((m) => m.remove());
    markers.current = [];
    for (const p of places) {
      const at = centroid(p.geojson);
      if (!at) continue;
      markers.current.push(new maplibregl.Marker({ element: labelEl(p) }).setLngLat(at).addTo(map));
    }
  }, [places, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setFilter(SELECTED, ["==", ["get", "name"], selected ?? ""]);
  }, [selected, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setLayoutProperty("satellite", "visibility", base === "satellite" ? "visible" : "none");
    map.setLayoutProperty("street", "visibility", base === "street" ? "visible" : "none");
  }, [base, ready]);

  return (
    <div
      ref={box}
      data-testid="paddock-map"
      className={cn("relative h-[38rem] min-h-[26rem] w-full overflow-hidden rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)]", className)}
    >
      <button
        type="button"
        className="absolute left-2 top-2 z-10 rounded-md bg-white/90 px-2.5 py-1 text-[11px] font-medium text-[#374151] shadow"
        onClick={() => setBase((b) => (b === "satellite" ? "street" : "satellite"))}
      >
        {base === "satellite" ? "Street map" : "Satellite"}
      </button>
    </div>
  );
}
