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
  "herds",
  "events",
  "health",
  "reports",
  "feeding",
  "concentrate",
  "stock",
  "rations",
  "ration-editor",
  "procurement",
  "movement",
  "calving",
  "service",
  "diagnosis",
  "husbandry",
  "abortion",
  "heat",
  "weight",
  "performance",
  "forecast",
  "paddocks",
  "shoats",
  "check-up",
  "treatment",
  "health-case",
  "culling",
  "settings",
  "notifications",
  "transactions",
  "costs",
  "labour",
] as const;

export type View = (typeof VIEWS)[number];

const KNOWN: ReadonlySet<string> = new Set<string>(VIEWS);

/** Feeding is the surface this frontend actually implements, so it is where an
 *  unrecognised or empty hash lands. */
export const DEFAULT_VIEW: View = "feeding";

export function isView(v: string): v is View {
  return KNOWN.has(v);
}

/**
 * Old routes that now live on another screen. A bookmark or a link in a
 * message to `#/feed-design` still opens: Feed Design and the Ration Editor
 * were two editors for the same recipe, and are one screen now.
 */
export const ALIASES: Readonly<Record<string, View>> = {
  "feed-design": "ration-editor",
};

function firstSegment(hash: string): string {
  const raw = (hash || "").replace(/^#\/?/, "");
  return (raw.split("?")[0].split("/").filter(Boolean)[0] || "").toLowerCase();
}

/** The view a hash names, following an old route to its new home. */
export function viewOfHash(hash: string): View {
  const first = firstSegment(hash);
  if (first in ALIASES) return ALIASES[first];
  return first && isView(first) ? first : DEFAULT_VIEW;
}

/** The hash an old route should be replaced with, or null when it is current. */
export function redirectHash(hash: string): string | null {
  const first = firstSegment(hash);
  if (!(first in ALIASES)) return null;
  const query = (hash || "").includes("?") ? hash.slice(hash.indexOf("?")) : "";
  return `${routeHash(ALIASES[first])}${query}`;
}

/** What a hash asks of the screen it opens: `#/ration-editor?concentrate=X`. */
export function hashParams(hash: string = window.location.hash): URLSearchParams {
  const i = (hash || "").indexOf("?");
  return new URLSearchParams(i < 0 ? "" : hash.slice(i + 1));
}

function parseHash(): View {
  return viewOfHash(window.location.hash);
}

/** Rewrite an old route in place, so Back does not bounce through it. */
function followAlias() {
  const next = redirectHash(window.location.hash);
  if (next) window.history.replaceState(null, "", next);
}

export function routeHash(view: View): string {
  return `#/${view}`;
}

export function useRoute(): [View, (next: View) => void] {
  const [view, setView] = useState<View>(() => {
    followAlias();
    return parseHash();
  });

  useEffect(() => {
    const onChange = () => {
      followAlias();
      setView(parseHash());
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((next: View) => {
    const h = routeHash(next);
    if (window.location.hash !== h) window.location.hash = h;
  }, []);

  return [view, navigate];
}
