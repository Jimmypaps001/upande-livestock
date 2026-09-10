import { lazy, Suspense } from "react";
import { AppSidebar } from "@/components/AppSidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
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
const Rations = lazy(() =>
  import("@/pages/Rations").then((m) => ({ default: m.Rations })),
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

const TITLES: Record<View, string> = {
  dashboard: "Dashboard",
  animals: "Animals",
  events: "Events",
  health: "Health",
  production: "Production",
  reports: "Reports",
  feeding: "Feeding",
  concentrate: "Concentrate",
  stock: "Feed in Store",
  rations: "Rations",
  milking: "Milking",
  movement: "Movement",
  "drying-off": "Drying Off",
  calving: "Calving",
  service: "Service",
  diagnosis: "Pregnancy Diagnosis",
  husbandry: "Husbandry",
  abortion: "Abortion",
  weight: "Weight",
  "check-up": "Check Up",
  treatment: "Treatment",
  "health-case": "Health Case",
  disposal: "Disposal",
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
  dashboard: Dashboard,
  settings: Settings,
  notifications: Notifications,
  milking: Milking,
};

export function App() {
  const [view, navigate] = useRoute();
  const Built = PAGES[view];

  return (
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
  );
}
