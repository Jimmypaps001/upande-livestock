import { lazy, Suspense } from "react";
import { AppSidebar } from "@/components/AppSidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { Stub } from "@/pages/Stub";
import { useRoute, type View } from "@/lib/router";

// Feeding is the only built page, but it is loaded lazily anyway so the next
// slices can add pages without the first paint growing with them.
const Feeding = lazy(() =>
  import("@/pages/Feeding").then((m) => ({ default: m.Feeding })),
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
};

export function App() {
  const [view, navigate] = useRoute();

  return (
    <SidebarProvider>
      <AppSidebar view={view} onNavigate={navigate} />
      <SidebarInset>
        <Suspense
          fallback={
            <div className="px-6 py-7 text-[13px] text-[var(--sd-muted)]">Loading…</div>
          }
        >
          {view === "feeding" ? <Feeding /> : <Stub title={TITLES[view]} />}
        </Suspense>
      </SidebarInset>
    </SidebarProvider>
  );
}
