import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRightLeft,
  Baby,
  Beaker,
  Bell,
  ClipboardList,
  ClipboardPen,
  Droplets,
  FlaskConical,
  FileText,
  Heart,
  HeartPulse,
  Home,
  LayoutDashboard,
  Milk,
  PanelLeftClose,
  PanelLeftOpen,
  Scale,
  Scissors,
  ShoppingCart,
  SlidersHorizontal,
  Stethoscope,
  Sun,
  Trash2,
  TrendingDown,
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
import { SidebarUser } from "@/components/SidebarUser";
import { useUnreadNotifications } from "@/hooks/use-notifications";
import { routeHash, type View } from "@/lib/router";
import { cn } from "@/lib/utils";
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
      {
        view: "ration-editor",
        label: "Ration Editor",
        icon: ClipboardPen,
        hint: "Change what a herd is fed — it becomes the next mix",
      },
      {
        view: "procurement",
        label: "Procurement",
        icon: ShoppingCart,
        hint: "What to buy to keep the herds fed, in one request",
      },
    ],
  },
  {
    label: "Operations",
    items: [
      {
        view: "milking",
        label: "Milking",
        icon: Droplets,
        hint: "Record what a herd gave at one milking",
      },
      {
        view: "quality",
        label: "Quality",
        icon: FlaskConical,
        hint: "File the creamery's figures against a milking",
      },
      { view: "movement", label: "Movement", icon: ArrowRightLeft },
      { view: "drying-off", label: "Drying Off", icon: Sun },
      { view: "calving", label: "Calving", icon: Baby },
      { view: "heat", label: "Heat", icon: Sun },
      { view: "service", label: "Service", icon: Heart },
      { view: "diagnosis", label: "Pregnancy Diagnosis", icon: Activity },
      { view: "husbandry", label: "Husbandry", icon: Scissors },
      { view: "abortion", label: "Abortion", icon: Heart },
      { view: "weight", label: "Weight", icon: Scale },
      { view: "check-up", label: "Check Up", icon: Stethoscope },
      { view: "treatment", label: "Treatment", icon: Beaker },
      { view: "health-case", label: "Health Files", icon: HeartPulse },
      { view: "herds", label: "Herds", icon: Home },
      { view: "culling", label: "Culling", icon: Trash2 },
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
  "ration-editor",
  "procurement",
  "herds",
  "service",
  "diagnosis",
  "abortion",
  "drying-off",
  "heat",
  "check-up",
  "health-case",
  "weight",
  "husbandry",
  "movement",
  "calving",
  "treatment",
  "events",
  "production",
  "reports",
  "health",
  "culling",
  "settings",
  "notifications",
  "milking",
  "quality",
  "animals",
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
  const { unread } = useUnreadNotifications();

  // The footer is pinned: SidebarContent is the only flexible row in the card
  // (flex-1 min-h-0, overflow hidden) and the nav scrolls INSIDE the ScrollArea
  // it holds, so the footer below it never moves. `moreBelow` is the visual half
  // of that promise — the top border and shadow appear only while nav items are
  // still hidden under the footer, so it reads as sitting over a scrolling list
  // rather than as a permanent rule.
  const navRef = useRef<HTMLDivElement>(null);
  const [moreBelow, setMoreBelow] = useState(false);
  useEffect(() => {
    const vp = navRef.current?.querySelector<HTMLElement>(
      '[data-slot="scroll-area-viewport"]',
    );
    if (!vp) return;
    const update = () =>
      setMoreBelow(vp.scrollHeight - vp.scrollTop - vp.clientHeight > 1);
    update();
    vp.addEventListener("scroll", update, { passive: true });
    // ResizeObserver is not in every test environment, and a missing shadow is
    // not worth a blank sidebar.
    const RO = typeof ResizeObserver === "function" ? ResizeObserver : null;
    const ro = RO ? new RO(update) : null;
    if (ro) {
      ro.observe(vp);
      if (vp.firstElementChild) ro.observe(vp.firstElementChild);
    }
    return () => {
      vp.removeEventListener("scroll", update);
      ro?.disconnect();
    };
  }, [collapsed]);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        {/* Brand — prominent logo, thin divider, product name with an uppercase
            letter-spaced eyebrow beneath it. */}
        <div className="flex items-center gap-2.5 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:gap-0">
          {/* Logo links back to the Frappe desk (/app). */}
          <a
            href="/app"
            title="Open Frappe Desk"
            className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-full bg-background p-1.5 ring-1 ring-border/60 transition-[box-shadow] hover:ring-2 hover:ring-border group-data-[collapsible=icon]:size-[3rem]"
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
          <div
            className={cn(
              "grid min-w-0 flex-1 text-left leading-tight",
              // `hidden` is not animatable, so the name vanished on the first
              // frame and the rail spent the next 260ms closing over the space
              // it left. A 1fr -> 0fr column never measures the text, so there
              // is nothing for it to jump to either.
              "overflow-hidden",
              "grid-cols-[1fr] opacity-100",
              "group-data-[collapsible=icon]:grid-cols-[0fr] group-data-[collapsible=icon]:opacity-0",
            )}
          >
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
      <SidebarContent
        ref={navRef}
        className="overflow-hidden p-0 group-data-[collapsible=icon]:p-0"
      >
        <ScrollArea
          className={cn(
            "h-full w-full",
            // Radix wraps viewport content in a `display: table` div, which
            // sizes to its content rather than to the viewport. Collapsed, the
            // labels are hidden but still measure, so that div keeps the
            // EXPANDED width and every row is laid out against its left edge
            // instead of the rail's centre. Forcing it to block lets it take
            // the rail's width, so the rows have somewhere symmetrical to sit.
            "group-data-[collapsible=icon]:[&>[data-radix-scroll-area-viewport]>div]:!block",
          )}
        >
          <div
            className={cn(
              "flex flex-col gap-1 p-2",
              // Collapsed, this padding IS the centring. A row is 27.2px in
              // a 51px rail, so it wants (51 - 27.2) / 2 = 11.9px either
              // side, less the 1px the scroll viewport insets.
              "group-data-[collapsible=icon]:p-[0.8rem]",
            )}
          >
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
      <SidebarFooter
        className={cn(
          "transition-shadow duration-200",
          moreBelow &&
            "border-t border-sidebar-border shadow-[0_-6px_14px_-10px_rgba(10,10,10,0.16)]",
        )}
      >
        {/* Notifications — a normal sidebar item, pinned to the footer rather
            than listed under Herd: it is not a part of the herd, it is how the
            herd reaches you, and it must stay reachable without scrolling. */}
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              isActive={view === "notifications"}
              className="relative"
              title={
                unread
                  ? `${unread} unread notification${unread === 1 ? "" : "s"}`
                  : "Notifications"
              }
            >
              <a
                href={routeHash("notifications")}
                onClick={(e) => {
                  e.preventDefault();
                  onNavigate("notifications");
                }}
              >
                <Bell className="h-4 w-4" />
                <span>Notifications</span>
                {/* Never rendered at zero — a badge showing 0 is noise that
                    trains the eye to ignore the one that matters. Collapsed, it
                    rides the corner of the bell instead of the row's end. */}
                {unread > 0 && (
                  <span
                    aria-label={`${unread} unread`}
                    className="ml-auto inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--sd-sev-critical)] px-1 text-[10px] font-semibold tabular-nums text-white group-data-[collapsible=icon]:absolute group-data-[collapsible=icon]:top-0 group-data-[collapsible=icon]:right-0 group-data-[collapsible=icon]:ml-0"
                  >
                    {unread > 99 ? "99+" : unread}
                  </span>
                )}
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarSeparator />

        {/* Collapse / Expand — a normal sidebar item, pinned here. The label
            follows the state so the rail's one visible word is never a lie. */}
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
              <span>{collapsed ? "Expand" : "Collapse"}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarSeparator />

        {/* Back to Desk, beside the profile chip: a full page load out of this
            app and into Frappe's own workspace at /app. It sits here rather
            than in the nav above because it is not one of this app's surfaces —
            and because somebody new to the app must be able to leave it without
            hunting. A plain <a href>, deliberately: the desk is a different
            document, not a hash route. */}
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild title="Back to Desk — the Frappe workspace at /app">
              {/* No loading cover on the way out: Frappe raises its own the
                  moment /app starts loading, and two covers handing over to
                  each other is one more than the crossing needs. */}
              <a href="/app">
                <Home className="h-4 w-4" />
                <span>Back to Desk</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarUser />
      </SidebarFooter>
    </Sidebar>
  );
}
