import {
  Activity,
  ArrowRightLeft,
  Baby,
  Beaker,
  ClipboardList,
  ClipboardPen,
  Droplets,
  FileText,
  Heart,
  HeartPulse,
  LayoutDashboard,
  Milk,
  PanelLeftClose,
  PanelLeftOpen,
  Scale,
  Scissors,
  SlidersHorizontal,
  Stethoscope,
  Sun,
  Trash2,
  Utensils,
  Warehouse,
  Wheat,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { routeHash, type View } from "@/lib/router";
import upandeLogo from "@/assets/upande_logo.png";

type IconType = React.ComponentType<{ className?: string }>;

type NavItem = { view: View; label: string; icon: IconType; hint?: string };
type NavSection = { label: string; items: NavItem[] };

/**
 * The surfaces that exist on the farm today, so the shape of the app is
 * visible from the first slice. What is not built yet routes to a placeholder
 * that says so rather than miming a screen that does not work — see
 * pages/Stub.tsx.
 */
const NAV: NavSection[] = [
  {
    label: "Herd",
    items: [
      {
        view: "dashboard",
        label: "Dashboard",
        icon: LayoutDashboard,
        hint: "Milk production over time",
      },
      { view: "animals", label: "Animals", icon: ClipboardList },
      { view: "events", label: "Events", icon: Activity },
      { view: "health", label: "Health", icon: HeartPulse },
      { view: "production", label: "Production", icon: Milk },
      { view: "reports", label: "Reports", icon: FileText },
    ],
  },
  {
    label: "Feeding",
    items: [
      {
        view: "feeding",
        label: "Feeding",
        icon: Utensils,
        hint: "Mix and issue a herd's ration",
      },
      {
        view: "concentrate",
        label: "Concentrate",
        icon: Wheat,
        hint: "What to mix, and what it would take",
      },
      {
        view: "stock",
        label: "Feed in Store",
        icon: Warehouse,
        hint: "What the feed stores are holding",
      },
      {
        view: "rations",
        label: "Rations",
        icon: ClipboardPen,
        hint: "Which recipe each herd was fed, and the milk beside it",
      },
    ],
  },
  {
    label: "Operations",
    items: [
      { view: "milking", label: "Milking", icon: Droplets },
      { view: "movement", label: "Movement", icon: ArrowRightLeft },
      { view: "drying-off", label: "Drying Off", icon: Sun },
      { view: "calving", label: "Calving", icon: Baby },
      { view: "service", label: "Service", icon: Heart },
      { view: "diagnosis", label: "Pregnancy Diagnosis", icon: Activity },
      { view: "husbandry", label: "Husbandry", icon: Scissors },
      { view: "abortion", label: "Abortion", icon: Heart },
      { view: "weight", label: "Weight", icon: Scale },
      { view: "check-up", label: "Check Up", icon: Stethoscope },
      { view: "treatment", label: "Treatment", icon: Beaker },
      { view: "health-case", label: "Health Case", icon: HeartPulse },
      { view: "disposal", label: "Disposal", icon: Trash2 },
    ],
  },
  {
    label: "Configuration",
    items: [
      {
        view: "settings",
        label: "Settings",
        icon: SlidersHorizontal,
        hint: "The rules the whole farm runs on",
      },
    ],
  },
];

/** Which views this slice actually implements. The rest render a placeholder. */
export const BUILT_VIEWS: ReadonlySet<View> = new Set<View>([
  "dashboard",
  "feeding",
  "concentrate",
  "stock",
  "rations",
  "settings",
]);

export function AppSidebar({
  view,
  onNavigate,
}: {
  view: View;
  onNavigate: (next: View) => void;
}) {
  const { state, toggle } = useSidebar();
  const collapsed = state === "collapsed";

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        {/* Brand — prominent logo, thin divider, product name with an uppercase
            letter-spaced eyebrow beneath it. */}
        <div className="flex items-center gap-2.5 py-1 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:gap-0 group-data-[collapsible=icon]:py-0">
          {/* Logo links back to the Frappe desk (/app). */}
          <a
            href="/app"
            title="Open Frappe Desk"
            className="flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-background ring-1 ring-border/60 transition hover:ring-2 hover:ring-border group-data-[collapsible=icon]:size-7"
          >
            <img
              src={upandeLogo}
              alt="Upande"
              className="size-full object-contain"
            />
          </a>
          <div className="h-6 w-px shrink-0 bg-border group-data-[collapsible=icon]:hidden" />
          {/* Always rendered, hidden via CSS so the width animation plays around
              it without React inserting/removing nodes mid-transition. */}
          <div className="grid min-w-0 flex-1 text-left leading-tight group-data-[collapsible=icon]:hidden">
            <span className="truncate text-sm font-semibold tracking-[-0.01em] text-foreground">
              Upande Livestock
            </span>
            <span className="mt-0.5 truncate text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--sd-quiet)]">
              Herd &amp; Dairy Operations
            </span>
          </div>
        </div>
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent className="overflow-hidden p-0 group-data-[collapsible=icon]:p-0">
        <ScrollArea className="h-full w-full">
          <div className="flex flex-col gap-1 p-2 group-data-[collapsible=icon]:p-1">
            {NAV.map((section) => (
              <SidebarGroup key={section.label}>
                <SidebarGroupLabel>{section.label}</SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {section.items.map((item) => {
                      const Icon = item.icon;
                      const built = BUILT_VIEWS.has(item.view);
                      return (
                        <SidebarMenuItem key={item.view}>
                          <SidebarMenuButton
                            asChild
                            isActive={view === item.view}
                            title={
                              item.hint ||
                              (built ? item.label : `${item.label} — not built yet`)
                            }
                          >
                            <a
                              href={routeHash(item.view)}
                              onClick={(e) => {
                                e.preventDefault();
                                onNavigate(item.view);
                              }}
                            >
                              <Icon className="h-4 w-4" />
                              <span className={built ? "" : "text-[var(--sd-quiet)]"}>
                                {item.label}
                              </span>
                            </a>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      );
                    })}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            ))}
          </div>
        </ScrollArea>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={toggle}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? (
                <PanelLeftOpen className="h-4 w-4" />
              ) : (
                <PanelLeftClose className="h-4 w-4" />
              )}
              <span>Collapse</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
