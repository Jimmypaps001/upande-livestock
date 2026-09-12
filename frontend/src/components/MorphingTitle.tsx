import { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * The page title, as one piece of text that travels.
 *
 * There is exactly ONE title on screen. The heading and the pill each hold an
 * invisible copy that reserves the space the real text will occupy; the real
 * text is a single fixed element that flies between those two slots. That is
 * what makes it read as a title moving rather than one title being swapped for
 * another — the fault every version of this had before, and the reason two of
 * them were briefly visible at once.
 *
 * FLIP, in the usual sense: measure where it is, measure where it is going,
 * and animate the difference with a transform. Transform only — no top, no
 * left, no font-size — because those three lay the page out again on every
 * frame and this runs while somebody is scrolling.
 *
 * The flyer renders at the HEADING's size and scales DOWN into the pill. The
 * other direction would render 14px text and blow it up to 40, which is
 * exactly as blurry as it sounds.
 */

/** Overshoots, settles back. The "tip-tap" — it arrives, bumps, and sits. */
const BOUNCE = "cubic-bezier(0.34, 1.56, 0.64, 1)";
const DURATION = 460;

interface Slot {
  x: number;
  y: number;
  size: number;
}

function slotOf(el: HTMLElement | null): Slot | null {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const size = parseFloat(getComputedStyle(el).fontSize) || 16;
  return { x: r.left, y: r.top, size };
}

export function MorphingTitle({
  title,
  headingSlot,
  dockSlot,
  docked,
}: {
  title: string;
  headingSlot: React.RefObject<HTMLElement | null>;
  dockSlot: React.RefObject<HTMLElement | null>;
  docked: boolean;
}) {
  const flyer = useRef<HTMLSpanElement | null>(null);
  const [animating, setAnimating] = useState(false);
  const first = useRef(true);

  // Put the flyer over whichever slot currently owns the title. While undocked
  // this runs on every scrolled frame, because the heading it is tracking is
  // moving up the screen; while docked the pill does not move and this settles.
  useLayoutEffect(() => {
    const el = flyer.current;
    const from = slotOf(headingSlot.current);
    const to = slotOf(dockSlot.current);
    if (!el || !from || !to) return;

    const target = docked ? to : from;
    const scale = docked ? to.size / from.size : 1;
    el.style.fontSize = `${from.size}px`;
    el.style.transform =
      `translate3d(${target.x}px, ${target.y}px, 0) scale(${scale})`;
  });

  // Animate only the crossing, never the tracking. A transition left on while
  // the flyer follows a scrolling heading makes it lag the page by its own
  // duration, which reads as the text sliding around loose.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    setAnimating(true);
    const t = window.setTimeout(() => setAnimating(false), DURATION + 60);
    return () => window.clearTimeout(t);
  }, [docked]);

  return (
    <>
      <span
        ref={flyer}
        aria-hidden
        className="pointer-events-none fixed left-0 top-0 z-50 origin-top-left whitespace-nowrap font-semibold leading-[1.05] tracking-[-0.03em] text-[var(--sd-ink)] will-change-transform"
        style={{
          transition: animating ? `transform ${DURATION}ms ${BOUNCE}` : "none",
        }}
      >
        {title}
      </span>
    </>
  );
}
