import { useCallback, useEffect, useState } from "react";

/**
 * Hash routing — one segment, one surface: `#/feeding`, `#/animals`.
 *
 * A hash router rather than a history one because the page is served by Frappe
 * at a single route (/livestock_app); a path router would need a server-side
 * catch-all that does not exist.
 */

export const VIEWS = [
  "dashboard",
  "animals",
  "quality",
  "events",
  "health",
  "production",
  "reports",
  "feeding",
  "concentrate",
  "stock",
  "rations",
  "projection",
  "procurement",
  "milking",
  "movement",
  "drying-off",
  "calving",
  "service",
  "diagnosis",
  "husbandry",
  "abortion",
  "weight",
  "check-up",
  "treatment",
  "health-case",
  "culling",
  "settings",
  "notifications",
] as const;

export type View = (typeof VIEWS)[number];

const KNOWN: ReadonlySet<string> = new Set<string>(VIEWS);

/** Feeding is the surface this frontend actually implements, so it is where an
 *  unrecognised or empty hash lands. */
export const DEFAULT_VIEW: View = "feeding";

export function isView(v: string): v is View {
  return KNOWN.has(v);
}

function parseHash(): View {
  const raw = (window.location.hash || "").replace(/^#\/?/, "");
  const first = raw.split("?")[0].split("/").filter(Boolean)[0];
  return first && isView(first.toLowerCase()) ? (first.toLowerCase() as View) : DEFAULT_VIEW;
}

export function routeHash(view: View): string {
  return `#/${view}`;
}

export function useRoute(): [View, (next: View) => void] {
  const [view, setView] = useState<View>(parseHash);

  useEffect(() => {
    const onChange = () => setView(parseHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((next: View) => {
    const h = routeHash(next);
    if (window.location.hash !== h) window.location.hash = h;
  }, []);

  return [view, navigate];
}
