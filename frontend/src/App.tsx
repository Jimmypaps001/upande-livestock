import { lazy, Suspense, useEffect } from "react";
import { AppSidebar } from "@/components/AppSidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/Toast";
import { PageSkeleton } from "@/components/Loading";
import { Stub } from "@/pages/Stub";
import { useRoute, type View } from "@/lib/router";

/**
 * Every chunk's loader, kept so they can be warmed after first paint.
 *
 * SWITCHING PAGES SHOULD BE WAITING FOR DATA, NOT FOR CODE. Lazy routes mean
 * first paint never pulls the whole app down a rural line — which is right —
 * but it also meant every first visit to a screen stopped on a bare "Loading…"
 * while its JavaScript arrived, and only THEN started asking for the farm's
 * figures. Two waits, one of them invisible to the skeletons built for the
 * other.
 *
 * So the chunks are fetched quietly once the first page is up and the browser
 * is idle. By the time anybody clicks, the code is in cache and the only thing
 * left to wait for is the data — which is what the skeletons are for.
 */
const CHUNKS: Array<() => Promise<unknown>> = [];

function page<T extends React.ComponentType<Record<string, never>>>(
  load: () => Promise<{ default: T }>,
) {
  CHUNKS.push(load);
  return lazy(load);
}

/** Pull every route's code in the background, gently and only once. */
function warmChunks() {
  let warmed = false;
  return () => {
    if (warmed) return;
    warmed = true;
    const idle =
      (window as unknown as { requestIdleCallback?: (fn: () => void) => void })
        .requestIdleCallback || ((fn: () => void) => window.setTimeout(fn, 400));
    idle(() => {
      // One at a time: a rural connection asked for twenty chunks at once
      // serves the one the operator is waiting for last.
      void CHUNKS.reduce(
        (queue, load) => queue.then(() => load().then(() => undefined, () => undefined)),
        Promise.resolve(),
      );
    });
  };
}

const warm = warmChunks();

// Each built page is loaded lazily, so first paint never pulls the whole app
// and the next slices can add pages without growing it.
const Feeding = page(() =>
  import("@/pages/Feeding").then((m) => ({ default: m.Feeding })),
);
const Concentrate = page(() =>
  import("@/pages/Concentrate").then((m) => ({ default: m.Concentrate })),
);
const Stock = page(() => import("@/pages/Stock").then((m) => ({ default: m.Stock })));
const Quality = page(() =>
  import("@/pages/Quality").then((m) => ({ default: m.Quality })),
);
const Rations = page(() =>
  import("@/pages/Rations").then((m) => ({ default: m.Rations })),
);
const Animals = page(() =>
  import("@/pages/Animals").then((m) => ({ default: m.Animals })),
);
const Dashboard = page(() =>
  import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard })),
);
const Settings = page(() =>
  import("@/pages/Settings").then((m) => ({ default: m.Settings })),
);
const Notifications = page(() =>
  import("@/pages/Notifications").then((m) => ({ default: m.Notifications })),
);
const Milking = page(() =>
  import("@/pages/Milking").then((m) => ({ default: m.Milking })),
);
const Culling = page(() =>
  import("@/pages/Culling").then((m) => ({ default: m.Culling })),
);
const Procurement = page(() =>
  import("@/pages/Procurement").then((m) => ({ default: m.Procurement })),
);
const Herds = page(() => import("@/pages/Herds").then((m) => ({ default: m.Herds })));

// The breeding calendar and the health screens are five and four exports of
// one module each: they share a scaffold, so splitting them into nine chunks
// would ship the same component nine times.
const Service = page(() => import("@/pages/Breeding").then((m) => ({ default: m.Service })));
const Diagnosis = page(() => import("@/pages/Breeding").then((m) => ({ default: m.Diagnosis })));
const Abortion = page(() => import("@/pages/Breeding").then((m) => ({ default: m.Abortion })));
const DryingOff = page(() => import("@/pages/Breeding").then((m) => ({ default: m.DryingOff })));
const Heat = page(() => import("@/pages/Breeding").then((m) => ({ default: m.Heat })));
const CheckUp = page(() => import("@/pages/Health").then((m) => ({ default: m.CheckUp })));
const HealthCases = page(() =>
  import("@/pages/HealthCases").then((m) => ({ default: m.HealthCases })),
);
const Weight = page(() => import("@/pages/Weights").then((m) => ({ default: m.Weights })));
const Husbandry = page(() => import("@/pages/Husbandry").then((m) => ({ default: m.Husbandry })));
const Movement = page(() => import("@/pages/Movement").then((m) => ({ default: m.Movement })));
const RationEditor = page(() =>
  import("@/pages/RationEditor").then((m) => ({ default: m.RationEditor })),
);
const Calving = page(() => import("@/pages/Calving").then((m) => ({ default: m.Calving })));
const Treatment = page(() => import("@/pages/Treatment").then((m) => ({ default: m.Treatment })));
// The four read-only views share a loader and nothing else heavy, so they ship
// as one chunk rather than four copies of it.
const Events = page(() => import("@/pages/Insights").then((m) => ({ default: m.Events })));
const Production = page(() => import("@/pages/Insights").then((m) => ({ default: m.Production })));
const Reports = page(() => import("@/pages/Insights").then((m) => ({ default: m.Reports })));
const HealthDashboard = page(() =>
  import("@/pages/HealthDashboard").then((m) => ({ default: m.HealthDashboard })),
);

const TITLES: Record<View, string> = {
  dashboard: "Dashboard",
  animals: "Animals",
  herds: "Herds",
  events: "Events",
  health: "Health",
  production: "Production",
  reports: "Reports",
  feeding: "Feeding",
  concentrate: "Concentrate",
  stock: "Feed in Store",
  rations: "Rations",
  "ration-editor": "Ration Editor",
  procurement: "Procurement",
  milking: "Milking",
  quality: "Quality",
  movement: "Movement",
  "drying-off": "Drying Off",
  calving: "Calving",
  service: "Service",
  diagnosis: "Pregnancy Diagnosis",
  husbandry: "Husbandry",
  abortion: "Abortion",
  heat: "Heat",
  weight: "Weight",
  "check-up": "Check Up",
  treatment: "Treatment",
  "health-case": "Health Files",
  culling: "Culling",
  settings: "Settings",
  notifications: "Notifications",
};

/** The surfaces this frontend implements. Everything else renders a
 *  placeholder that says the desk block still does the work. */
const PAGES: Partial<Record<View, React.ComponentType>> = {
  feeding: Feeding,
  concentrate: Concentrate,
  stock: Stock,
  rations: Rations,
  animals: Animals,
  dashboard: Dashboard,
  settings: Settings,
  notifications: Notifications,
  milking: Milking,
  quality: Quality,
  culling: Culling,
  procurement: Procurement,
  herds: Herds,
  service: Service,
  diagnosis: Diagnosis,
  abortion: Abortion,
  "drying-off": DryingOff,
  heat: Heat,
  "check-up": CheckUp,
  "health-case": HealthCases,
  weight: Weight,
  husbandry: Husbandry,
  movement: Movement,
  calving: Calving,
  treatment: Treatment,
  events: Events,
  production: Production,
  reports: Reports,
  health: HealthDashboard,
  "ration-editor": RationEditor,
};

export function App() {
  const [view, navigate] = useRoute();
  const Built = PAGES[view];

  // Once the first screen is on the page, quietly pull the rest of the code so
  // the next click waits for data and nothing else.
  useEffect(warm, []);

  return (
    // One provider at the root: every icon-only control on every page needs a
    // tooltip to say what it does, and a per-card provider would restart the
    // shared open/close delay each time the pointer crossed a card boundary.
    <TooltipProvider delayDuration={200}>
      <ToastProvider>
      <SidebarProvider>
        <AppSidebar view={view} onNavigate={navigate} />
      {/* min-w-0 so a wide table inside the workspace scrolls in its own box
          instead of refusing to shrink and pushing the page sideways. */}
        <SidebarInset className="min-w-0">
          {/* A page shape, not the word "Loading". Once the chunks are warm
              this is rarely seen at all — and when it is (a cold first visit,
              a slow line) it is the same silhouette the page settles into,
              rather than a blank that reflows the moment it arrives. */}
          <Suspense fallback={<PageSkeleton />}>
            {Built ? <Built /> : <Stub title={TITLES[view]} />}
          </Suspense>
        </SidebarInset>
      </SidebarProvider>
      </ToastProvider>
    </TooltipProvider>
  );
}
