import { lazy, Suspense } from "react";
import { AppSidebar } from "@/components/AppSidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Stub } from "@/pages/Stub";
import { useRoute, type View } from "@/lib/router";

// Each built page is loaded lazily, so first paint never pulls the whole app
// and the next slices can add pages without growing it.
const Feeding = lazy(() =>
  import("@/pages/Feeding").then((m) => ({ default: m.Feeding })),
);
const Concentrate = lazy(() =>
  import("@/pages/Concentrate").then((m) => ({ default: m.Concentrate })),
);
const Stock = lazy(() => import("@/pages/Stock").then((m) => ({ default: m.Stock })));
const Quality = lazy(() =>
  import("@/pages/Quality").then((m) => ({ default: m.Quality })),
);
const Rations = lazy(() =>
  import("@/pages/Rations").then((m) => ({ default: m.Rations })),
);
const Animals = lazy(() =>
  import("@/pages/Animals").then((m) => ({ default: m.Animals })),
);
const Dashboard = lazy(() =>
  import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard })),
);
const Settings = lazy(() =>
  import("@/pages/Settings").then((m) => ({ default: m.Settings })),
);
const Notifications = lazy(() =>
  import("@/pages/Notifications").then((m) => ({ default: m.Notifications })),
);
const Milking = lazy(() =>
  import("@/pages/Milking").then((m) => ({ default: m.Milking })),
);
const Culling = lazy(() =>
  import("@/pages/Culling").then((m) => ({ default: m.Culling })),
);
const Projection = lazy(() =>
  import("@/pages/Projection").then((m) => ({ default: m.Projection })),
);
const Procurement = lazy(() =>
  import("@/pages/Procurement").then((m) => ({ default: m.Procurement })),
);
const Herds = lazy(() => import("@/pages/Herds").then((m) => ({ default: m.Herds })));

// The breeding calendar and the health screens are five and four exports of
// one module each: they share a scaffold, so splitting them into nine chunks
// would ship the same component nine times.
const Service = lazy(() => import("@/pages/Breeding").then((m) => ({ default: m.Service })));
const Diagnosis = lazy(() => import("@/pages/Breeding").then((m) => ({ default: m.Diagnosis })));
const Abortion = lazy(() => import("@/pages/Breeding").then((m) => ({ default: m.Abortion })));
const DryingOff = lazy(() => import("@/pages/Breeding").then((m) => ({ default: m.DryingOff })));
const Heat = lazy(() => import("@/pages/Breeding").then((m) => ({ default: m.Heat })));
const CheckUp = lazy(() => import("@/pages/Health").then((m) => ({ default: m.CheckUp })));
const HealthCase = lazy(() => import("@/pages/Health").then((m) => ({ default: m.HealthCase })));
const Weight = lazy(() => import("@/pages/Health").then((m) => ({ default: m.Weight })));
const Husbandry = lazy(() => import("@/pages/Health").then((m) => ({ default: m.Husbandry })));
const Movement = lazy(() => import("@/pages/Movement").then((m) => ({ default: m.Movement })));

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
  projection: "Feed Projection",
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
  "health-case": "Health Case",
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
  projection: Projection,
  procurement: Procurement,
  herds: Herds,
  service: Service,
  diagnosis: Diagnosis,
  abortion: Abortion,
  "drying-off": DryingOff,
  heat: Heat,
  "check-up": CheckUp,
  "health-case": HealthCase,
  weight: Weight,
  husbandry: Husbandry,
  movement: Movement,
};

export function App() {
  const [view, navigate] = useRoute();
  const Built = PAGES[view];

  return (
    // One provider at the root: every icon-only control on every page needs a
    // tooltip to say what it does, and a per-card provider would restart the
    // shared open/close delay each time the pointer crossed a card boundary.
    <TooltipProvider delayDuration={200}>
      <SidebarProvider>
        <AppSidebar view={view} onNavigate={navigate} />
      {/* min-w-0 so a wide table inside the workspace scrolls in its own box
          instead of refusing to shrink and pushing the page sideways. */}
        <SidebarInset className="min-w-0">
          <Suspense
            fallback={
              <div className="px-4 py-4 text-[13px] text-[var(--sd-muted)] md:px-6 md:py-6">
                Loading…
              </div>
            }
          >
            {Built ? <Built /> : <Stub title={TITLES[view]} />}
          </Suspense>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}
