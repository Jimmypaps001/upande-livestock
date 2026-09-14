import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Figure, FigureRow } from "@/components/Figure";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChartSkeleton } from "@/components/Loading";
import { MILK_CHART_HEIGHT } from "@/components/dashboard/MilkChart";

/**
 * The point of a skeleton is that the box does not change.
 *
 * A spinner says "wait". A skeleton says "wait, and here is where it will be" —
 * which is only worth building if it is true. A placeholder that is not the
 * height of its content makes the page jump when the data lands, which is worse
 * than the spinner it replaced, so what is tested is the geometry and not the
 * appearance.
 */
describe("loading into place", () => {
  it("a loading figure occupies the same box as a loaded one", () => {
    const { container: loadingBox } = render(
      <FigureRow>
        <Figure loading label="In this window" value="—" />
      </FigureRow>,
    );
    const { container: loadedBox } = render(
      <FigureRow>
        <Figure label="In this window" value="5,106.00" unit="kg" hint="30 days recorded" />
      </FigureRow>,
    );
    const cls = (c: HTMLElement) =>
      (c.querySelector("[class*='px-5']") as HTMLElement).className;
    // Same wrapper, same paddings, same gaps — because it is literally the same
    // element, rendered by the same component.
    expect(cls(loadingBox)).toBe(cls(loadedBox));
  });

  it("keeps the label visible while the number is missing", () => {
    // Half the value of a skeleton is that you can already read what is coming.
    render(<Figure loading label="Best day" value="—" />);
    expect(screen.getByText("Best day")).toBeTruthy();
  });

  it("the chart placeholder is the height of the chart it stands in for", () => {
    const { container } = render(<ChartSkeleton height={MILK_CHART_HEIGHT} />);
    const box = container.firstElementChild as HTMLElement;
    expect(box.style.height).toBe(`${MILK_CHART_HEIGHT}px`);
    expect(MILK_CHART_HEIGHT).toBe(320);
  });
});

/**
 * And the dashboard hosts the feed projection rather than the sidebar carrying
 * a second entry for it.
 */
const call = vi.fn(async (method?: string) => {
  const m = method || "";
  if (m.includes("feed_projection")) {
    return { ok: true, start: "2026-09-14", days: 30, dates: ["2026-09-14"],
             basis: "today's head counts and today's rations", items: [], running_out: [] };
  }
  return { ok: true, points: [], summary: {}, herds: [] };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Dashboard } = await import("@/pages/Dashboard");

describe("the dashboard", () => {
  it("offers milk and feed as two tabs of one question", async () => {
    render(
      <TooltipProvider>
      <ToastProvider>
        <Dashboard />
      </ToastProvider>
    </TooltipProvider>,
    );
    await waitFor(() => expect(screen.getByRole("tab", { name: /Milk production/ })).toBeTruthy());
    expect(screen.getByRole("tab", { name: /Feed projection/ })).toBeTruthy();
  });
});
