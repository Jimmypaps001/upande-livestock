/**
 * The cover that holds the screen while a page load is in flight.
 *
 * Frappe shows one on every desk navigation; crossing between the desk and
 * this app is a full document load in both directions, and without a cover
 * that crossing is a flash of half-painted page. The markup and the styling
 * live in `www/livestock_app.html` so the cover is on screen in the first
 * frame, before this bundle — or its stylesheet — has loaded. These two
 * functions only raise and lower it.
 */

const ID = "lv-splash";
const FADE_MS = 280;

/** Fade the cover out and take it out of the document. */
export function dismissSplash(): void {
  const el = document.getElementById(ID);
  if (!el) return;
  el.classList.add("lv-leaving");
  window.setTimeout(() => el.remove(), FADE_MS + 40);
}

/**
 * Put the cover back up, for a navigation that leaves this app.
 *
 * Rebuilt rather than kept hidden, because dismissSplash removes it: a cover
 * that lingered in the DOM for the whole session would be one stray CSS change
 * away from covering the app.
 *
 * Styling is inline here for the same reason it is inline in the shell — this
 * runs at the moment of leaving, and a class whose stylesheet is being torn
 * down paints nothing.
 */
export function raiseSplash(): void {
  if (document.getElementById(ID)) return;
  const el = document.createElement("div");
  el.id = ID;
  el.className = "lv-splash";
  el.setAttribute("style", [
    "position:fixed",
    "inset:0",
    "z-index:2147483000",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "background:#fbfaf6",
  ].join(";"));

  const img = document.createElement("img");
  img.src = "/assets/upande_livestock/images/upande_logo.png";
  img.alt = "Upande Livestock";
  img.setAttribute(
    "style",
    "width:76px;height:76px;border-radius:18px;display:block;animation:lv-breathe 1400ms ease-in-out infinite",
  );

  el.appendChild(img);
  document.body.appendChild(el);
}

/**
 * Leave for another document, showing the cover on the way.
 *
 * The navigation is deferred by one frame so the browser paints the cover
 * before it starts tearing this page down — assign location.href in the same
 * tick and the cover never appears.
 */
export function leaveTo(href: string): void {
  raiseSplash();
  window.requestAnimationFrame(() => {
    window.setTimeout(() => {
      window.location.href = href;
    }, 60);
  });
}
