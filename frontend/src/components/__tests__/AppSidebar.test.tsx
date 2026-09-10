import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

/**
 * The sidebar footer's structural contract.
 *
 * There is no browser in this environment, so nothing here claims the footer
 * *looks* pinned. What it does assert is the arrangement that makes it pinned,
 * which is the part that silently regresses: the nav has to live inside the
 * ScrollArea and the footer has to live OUTSIDE it. Move the footer in — or drop
 * the ScrollArea and let SidebarContent scroll itself — and the footer scrolls
 * away with the list, which is exactly the bug this replaces.
 */

const unread = vi.hoisted(() => ({ value: 0 }));
vi.mock("@/hooks/use-notifications", () => ({
  useUnreadNotifications: () => ({
    unread: unread.value,
    refresh: async () => {},
    setUnread: () => {},
  }),
}));

import { AppSidebar } from "@/components/AppSidebar";
import { SidebarProvider } from "@/components/ui/sidebar";

beforeAll(() => {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  // Radix's ScrollArea measures itself; jsdom has no ResizeObserver.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  window.LIVESTOCK = {
    bootstrap: {
      user: "dairy@upande.com",
      full_name: "Jane Kamau",
      user_image: "",
      site_name: "kaitet",
      roles: [],
    },
  };
});

afterEach(() => {
  unread.value = 0;
  cleanup();
});

function mount() {
  return render(
    <SidebarProvider>
      <AppSidebar view="feeding" onNavigate={() => {}} />
    </SidebarProvider>,
  );
}

function footer(container: HTMLElement): HTMLElement {
  const el = container.querySelector<HTMLElement>('[data-sidebar="footer"]');
  if (!el) throw new Error("no sidebar footer rendered");
  return el;
}

describe("sidebar footer", () => {
  it("sits outside the scrolling nav, so the nav can scroll under it", () => {
    const { container } = mount();
    const content = container.querySelector<HTMLElement>('[data-sidebar="content"]')!;
    const scroller = content.querySelector<HTMLElement>('[data-slot="scroll-area"]')!;
    const viewport = scroller.querySelector<HTMLElement>(
      '[data-slot="scroll-area-viewport"]',
    )!;

    // The nav really is inside the scrolling viewport…
    expect(viewport.textContent).toContain("Milking");
    // …and the footer really is not.
    expect(scroller.contains(footer(container))).toBe(false);
    // The only flexible row is the content; the footer is pushed to the bottom
    // of the card and the content is the thing that gives.
    expect(content.className).toContain("flex-1");
    expect(content.className).toContain("min-h-0");
    expect(footer(container).className).toContain("mt-auto");
  });

  it("carries notifications, collapse and back-to-desk, each with a title", () => {
    const { container } = mount();
    const f = footer(container);
    const titles = Array.from(f.querySelectorAll("[title]")).map((e) =>
      e.getAttribute("title"),
    );
    // Icon mode hides every label, so each footer row must be identifiable by
    // hover alone.
    expect(titles).toContain("Notifications");
    expect(titles).toContain("Collapse sidebar");
    expect(titles.some((t) => t?.startsWith("Back to Desk"))).toBe(true);
    expect(titles.some((t) => t?.includes("dairy@upande.com"))).toBe(true);
  });

  it("sends Back to Desk to the Frappe desk with a real page load", () => {
    const { container } = mount();
    const link = footer(container).querySelector<HTMLAnchorElement>('a[href="/app"]')!;
    expect(link).toBeTruthy();
    expect(link.textContent).toContain("Back to Desk");
  });

  it("shows the profile chip beside it", () => {
    const { container } = mount();
    expect(footer(container).textContent).toContain("Jane Kamau");
  });

  it("renders no badge at zero unread", () => {
    const { container } = mount();
    expect(footer(container).querySelector("[aria-label$='unread']")).toBeNull();
  });

  it("renders the badge once there is something to read, and caps it at 99+", () => {
    unread.value = 3;
    const first = mount();
    expect(
      footer(first.container).querySelector("[aria-label='3 unread']")?.textContent,
    ).toBe("3");
    cleanup();

    unread.value = 250;
    const second = mount();
    expect(
      footer(second.container).querySelector("[aria-label='250 unread']")?.textContent,
    ).toBe("99+");
  });
});

describe("sidebar nav", () => {
  it("lists Milking as a built page rather than a placeholder", () => {
    mount();
    const link = screen.getByRole("link", { name: /Milking/ });
    expect(link.getAttribute("href")).toBe("#/milking");
    expect(link.querySelector("span")?.className).not.toContain("sd-quiet");
  });
});
