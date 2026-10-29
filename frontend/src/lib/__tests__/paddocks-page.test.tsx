import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/Toast";

// maplibre needs WebGL: stand in a map that records what it was given
const added: { sources: Record<string, unknown>; markers: string[] } = { sources: {}, markers: [] };
vi.mock("maplibre-gl", () => {
  class Map {
    private handlers: Record<string, () => void> = {};
    constructor(public opts: unknown) {}
    addControl() {}
    once(ev: string, fn: () => void) { setTimeout(fn, 0); return this; }
    on() {}
    addSource(id: string, src: unknown) { added.sources[id] = src; }
    addLayer() {}
    getSource() { return { setData: (d: unknown) => (added.sources.places = { data: d }) }; }
    setFilter() {}
    setLayoutProperty() {}
    fitBounds() {}
    getCanvas() { return { style: {} }; }
    remove() {}
  }
  class Marker {
    constructor(public o: { element: HTMLElement }) {}
    setLngLat() { return this; }
    addTo() { added.markers.push(this.o.element.textContent || ""); return this; }
    remove() {}
  }
  class NavigationControl {}
  return { default: { Map, Marker, NavigationControl } };
});
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

const ring = (w: number) => [[w, 0], [w + 1, 0], [w + 1, 1], [w, 1], [w, 0]];
const gj = (w: number) => ({ type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring(w)] } }] });
const place = (o: Record<string, unknown>) => ({
  warehouse: "Paddock A1 - MUT", label: "Paddock A1", kind: "Paddock", area_ha: 0.1459, geojson: gj(0), state: "occupied", heads: 98,
  head_per_ha: 671.7, herds: [{ herd: "Lactation Group 1", heads: 98, colour: "#2f7d4f" }], colour: "#2f7d4f", feed_kg: 0, ...o,
});
let payload: unknown;
const call = vi.fn(async (method?: string) => ((method || "").endsWith("get_paddock_map") ? payload : {}));
vi.mock("@/lib/frappe", async () => ({ ...(await vi.importActual<object>("@/lib/frappe")), call }));

const { Paddocks } = await import("@/pages/Paddocks");
const draw = () =>
  render(
    <TooltipProvider>
      <ToastProvider>
        <Paddocks />
      </ToastProvider>
    </TooltipProvider>,
  );

const rotation = (o: Record<string, unknown>) => ({
  paddocks: 7, grazing_herds: 5, per_herd: 1.4, needed_per_herd: 6, needed_total: 30, shortfall: 23, rest_days: 2.8,
  target_rest_days: 35, graze_days: 7, enough: false, grazing_ha: 1.03, grazing_head: 250, head_per_ha: 242.6,
  message: "7 paddocks for 5 grazing herds is 1.4 per herd: each paddock rests about 2.8 days.", ...o,
});

describe("the paddock map page", () => {
  beforeEach(() => {
    added.sources = {};
    added.markers = [];
    payload = {
      places: [
        place({}),
        place({ warehouse: "Paddock A2 - MUT", label: "Paddock A2", state: "resting", heads: 0, herds: [], colour: "#9aa59a", head_per_ha: null, geojson: gj(2) }),
        place({ warehouse: "Feedlot Pen 1 - MUT", label: "Feedlot Pen 1", kind: "Pen", heads: 90, herds: [{ herd: "Starters", heads: 90, colour: "#3b6fb6" }], colour: "#3b6fb6", geojson: gj(4) }),
      ],
      herds: [
        { herd: "Lactation Group 1", herd_class: "Breeding", paddock: "Paddock A1 - MUT", heads: 98, colour: "#2f7d4f", grazing: true },
        { herd: "Starters", herd_class: "Fattening", paddock: "Feedlot Pen 1 - MUT", heads: 90, colour: "#3b6fb6", grazing: false },
      ],
      unplaced: [],
      rotation: rotation({}),
      resting: ["Paddock A2"],
    };
  });

  it("states the paddocks per grazing herd and that it is not enough", async () => {
    draw();
    const note = await screen.findByTestId("rotation");
    expect(note.textContent).toContain("7 paddocks for 5 grazing herds is 1.4 per herd");
    expect(screen.getByText("Paddocks per herd").parentElement!.textContent).toContain("1.4");
    expect(screen.getByText("Paddocks per herd").parentElement!.textContent).toContain("6 needed to rotate");
  });

  it("labels each outline with the herd and head, resting ones as resting", async () => {
    draw();
    await waitFor(() => expect(added.markers.length).toBe(3));
    expect(added.markers).toContain("Lactation Group 198 head");
    expect(added.markers).toContain("Paddock A2Resting");
    expect(added.markers).toContain("Starters90 head");
  });

  it("hands the map one outline per place with its colour", async () => {
    draw();
    await waitFor(() => expect(added.sources.places).toBeTruthy());
    const fc = (added.sources.places as { data: { features: Array<{ properties: { colour: string; state: string } }> } }).data;
    expect(fc.features.map((f) => f.properties.state)).toEqual(["occupied", "resting", "occupied"]);
    expect(fc.features[1].properties.colour).toBe("#9aa59a");
  });

  it("lists every place with its herd, or resting", async () => {
    draw();
    const table = await screen.findByTestId("paddock-rows");
    const a2 = within(table).getByText("Paddock A2").closest("tr")!;
    expect(a2.textContent).toContain("Resting");
    expect(within(table).getByText("Feedlot Pen 1").closest("tr")!.textContent).toContain("Starters");
    expect(screen.getByTestId("paddock-legend").textContent).toContain("Lactation Group 1");
  });

  it("says nothing is wrong when there are enough paddocks, and names unplaced herds", async () => {
    payload = { ...(payload as object), unplaced: ["Weaner Heifers"], rotation: rotation({ enough: true, message: "30 paddocks for 5 grazing herds: enough." }) };
    draw();
    expect((await screen.findByTestId("rotation")).textContent).toContain("enough");
    expect(screen.getByTestId("unplaced").textContent).toContain("Weaner Heifers");
  });

  it("shows a refusal verbatim", async () => {
    payload = { error: "Not permitted." };
    draw();
    await waitFor(() => expect(screen.getByText("Not permitted.")).toBeTruthy());
  });
});
