import { useRef } from "react";

import { PageDock } from "@/components/PageDock";
import { MorphingTitle } from "@/components/MorphingTitle";
import { useDockProgress } from "@/lib/use-dock-progress";

/**
 * The frame every surface sits in.
 *
 * `flex-1` with padding and no max width: the workspace is whatever the
 * window leaves after the sidebar, and it reflows when the sidebar collapses
 * to its icon rail. A centred `max-w` column here would pin the content to
 * one width and leave a gutter on a wide screen — which is exactly what the
 * first slice did, and what this replaces.
 *
 * `min-w-0` matters as much as `flex-1`: without it a wide table inside a
 * flex child refuses to shrink and pushes the whole page into a horizontal
 * scroll. Wide content scrolls inside its own box instead.
 */
export function Page({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-6 px-4 py-4 md:px-6 md:py-6">
      {children}
    </div>
  );
}

export function PageHeading({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow: string;
  title: string;
  children?: React.ReactNode;
  /** Controls that belong to the page rather than to any one card. Right
   *  aligned on the title's own line from `md` up, stacked beneath it on a
   *  phone where there is no room beside a 40px heading. */
  actions?: React.ReactNode;
}) {
  // The heading owns its own dock rather than each page wiring one up. Every
  // surface in this app has a heading and every one of them scrolls, so making
  // it opt-in would mean eleven identical opt-ins and one page that forgot.
  const ref = useRef<HTMLElement | null>(null);
  const headingSlot = useRef<HTMLHeadingElement | null>(null);
  const dockSlot = useRef<HTMLSpanElement | null>(null);
  const progress = useDockProgress(ref);
  // One threshold, not a ramp: the title is a single element that flies, so
  // there is a moment it leaves rather than a stretch it dissolves over.
  const docked = progress >= 1;

  return (
    <>
      <header ref={ref} className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between md:gap-6">
          <div className="min-w-0">
            {/* The rule before the eyebrow is the scouting app's, and it earns
                its place: it stops a 10px tracked label floating unanchored
                above a 40px heading. */}
            <div className="mb-2 flex items-center gap-2.5 text-[11px] font-medium uppercase tracking-[0.2em] text-[var(--sd-quiet)]">
              <span className="h-px w-[18px] shrink-0 bg-[var(--sd-text)]" />
              <span className="truncate">{eyebrow}</span>
            </div>
            {/* The slot, not the title. It reserves the space and stays the
                page's real <h1> for anything reading the document; the text
                you can see is the flyer, which is aria-hidden. Opacity rather
                than visibility, because visibility:hidden would take the
                heading out of the accessibility tree with it. */}
            <h1
              ref={headingSlot}
              className="text-[28px] font-semibold leading-[1.05] tracking-[-0.03em] text-[var(--sd-ink)] opacity-0 md:text-[40px]"
            >
              {title}
            </h1>
          </div>
          {actions && (
            <div className="flex shrink-0 flex-wrap items-center gap-2 md:pt-1">
              {actions}
            </div>
          )}
        </div>
        {children && (
          <p className="max-w-[68ch] text-[13px] leading-relaxed text-[var(--sd-muted)]">
            {children}
          </p>
        )}
      </header>
      <PageDock
        eyebrow={eyebrow}
        title={title}
        docked={docked}
        titleSlot={dockSlot}
      />
      <MorphingTitle
        title={title}
        headingSlot={headingSlot}
        dockSlot={dockSlot}
        docked={docked}
      />
    </>
  );
}
