import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * The page's name, caught before it scrolls away.
 *
 * A 40px title is worth the room it takes at the top of a page and worth none
 * of it halfway down, so it leaves — and takes with it the one thing telling
 * you which of eleven surfaces you are looking at. The dock is that name given
 * somewhere to go: it slides down as the heading leaves and slides back up as
 * the heading returns, so the title is never in two places at once and never
 * in none.
 *
 * It is a real floating surface, so it reads as one: translucent, blurred, and
 * carrying the elevation-3 shadow the scale reserves for chrome over the page.
 * Sitting it flat on the paper would leave the reader guessing whether the
 * content had scrolled under it or stopped.
 *
 * An IntersectionObserver, not a scroll listener: the question is "is the
 * heading on screen", which is the one thing the observer answers natively and
 * a scroll handler only approximates — and it answers it without running code
 * on every frame of every scroll.
 */
export function PageDock({
  eyebrow,
  title,
  watch,
  children,
}: {
  eyebrow: string;
  title: string;
  /** The heading this shadows. The dock shows when it is off screen. */
  watch: React.RefObject<HTMLElement | null>;
  /** Controls to carry along — a refresh, a filter the page still needs. */
  children?: React.ReactNode;
}) {
  const [docked, setDocked] = useState(false);
  const frame = useRef<number | undefined>(undefined);

  useEffect(() => {
    const el = watch.current;
    if (!el || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        // One frame's grace. Without it a heading that lands exactly on the
        // boundary flickers the dock in and out as the page settles.
        window.cancelAnimationFrame(frame.current ?? 0);
        frame.current = window.requestAnimationFrame(() =>
          setDocked(!entry.isIntersecting),
        );
      },
      // The bottom of the heading has to clear the dock's own height before
      // the dock appears, or the two overlap for the length of that margin.
      { rootMargin: "-72px 0px 0px 0px", threshold: 0 },
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frame.current ?? 0);
    };
  }, [watch]);

  return (
    <div
      aria-hidden={!docked}
      className={cn(
        "pointer-events-none fixed inset-x-0 top-0 z-40 flex justify-center px-4 pt-3",
        "transition-[transform,opacity] duration-300 ease-out motion-reduce:transition-none",
        docked ? "translate-y-0 opacity-100" : "-translate-y-[140%] opacity-0",
      )}
    >
      <div
        className={cn(
          "pointer-events-auto flex max-w-full items-center gap-3 rounded-[var(--sd-radius-pill)]",
          "border border-[var(--sd-line-soft)] bg-[color-mix(in_srgb,var(--sd-card)_78%,transparent)]",
          "px-4 py-2 shadow-[var(--sd-shadow-3)] backdrop-blur-xl",
        )}
      >
        <span className="h-px w-3.5 shrink-0 bg-[var(--sd-text)]" aria-hidden />
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="truncate text-[14px] font-semibold tracking-[-0.01em] text-[var(--sd-ink)]">
            {title}
          </span>
          <span className="hidden truncate text-[11px] uppercase tracking-[0.14em] text-[var(--sd-quiet)] sm:inline">
            {eyebrow}
          </span>
        </span>
        {children && <span className="flex shrink-0 items-center gap-2">{children}</span>}
      </div>
    </div>
  );
}
