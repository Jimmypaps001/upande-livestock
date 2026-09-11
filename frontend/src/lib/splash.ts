/**
 * The cover that holds the screen while the app gets on its feet.
 *
 * Frappe shows one on every desk navigation; crossing between the desk and
 * this app is a full document load in both directions, and without a cover
 * that crossing is a flash of half-painted page. The markup and the styling
 * live in `www/livestock_app.html` so the cover is on screen in the first
 * frame, before this bundle — or its stylesheet — has loaded. This module only
 * decides when it comes down, and puts it back up on the way out.
 *
 * WHEN IT COMES DOWN. Three conditions, in order:
 *
 *  1. React has painted. Uncovering a root React has been handed but not yet
 *     drawn shows the blank frame the cover exists to hide.
 *  2. A second has passed. A cover that flashes off after thirty milliseconds
 *     is a flicker, not a transition — it reads as a glitch rather than as the
 *     app opening.
 *  3. The first data has landed. Every endpoint goes through `call` in
 *     lib/frappe, so the count of requests in flight is known here without a
 *     single page having to say anything; the cover waits for that count to
 *     reach zero rather than handing over a screen of empty figures.
 *
 * And a cap, because condition 3 is a promise this module cannot keep on its
 * own: an endpoint that hangs would otherwise trap the operator behind a logo
 * with no way past it. At the cap the cover comes down regardless and the page
 * shows whatever state it is in — which is at worst the same empty screen,
 * with the controls to do something about it.
 */

const ID = "lv-splash";
const FADE_MS = 280;
/** The floor. Below this the cover reads as a flicker. */
const MIN_MS = 1000;
/** The ceiling, when a request never comes back. */
const CAP_MS = 6000;

const openedAt =
  typeof performance !== "undefined" ? performance.now() : Date.now();

let painted = false;
let inFlight = 0;
let dismissed = false;
let timer: number | undefined;

function since(): number {
  const now = typeof performance !== "undefined" ? performance.now() : Date.now();
  return now - openedAt;
}

function hide(): void {
  if (dismissed) return;
  dismissed = true;
  const el = document.getElementById(ID);
  if (!el) return;
  el.classList.add("lv-leaving");
  window.setTimeout(() => el.remove(), FADE_MS + 40);
}

/** Re-evaluate the three conditions, and schedule the next look if it is not
 *  time yet. */
function settle(): void {
  if (dismissed || !painted) return;
  window.clearTimeout(timer);

  const waited = since();
  if (waited < MIN_MS) {
    timer = window.setTimeout(settle, MIN_MS - waited);
    return;
  }
  if (inFlight > 0 && waited < CAP_MS) {
    // Nothing to do: the request that finishes will call back in here. The
    // timer is only the backstop for one that never does.
    timer = window.setTimeout(settle, CAP_MS - waited);
    return;
  }
  hide();
}

/** Called once React has actually drawn something. */
export function markPainted(): void {
  painted = true;
  settle();
}

/** Bracketing for lib/frappe's `call`, so the cover knows what is outstanding. */
export function requestStarted(): void {
  inFlight += 1;
}

export function requestFinished(): void {
  inFlight = Math.max(0, inFlight - 1);
  settle();
}

/**
 * Put the cover back up, for a navigation that leaves this app.
 *
 * Rebuilt rather than kept hidden, because it is removed on the way in: one
 * that lingered in the DOM for the whole session would be a single stray CSS
 * change away from covering the app.
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
  el.setAttribute(
    "style",
    [
      "position:fixed",
      "inset:0",
      "z-index:2147483000",
      "display:flex",
      "align-items:center",
      "justify-content:center",
      "background:#ffffff",
    ].join(";"),
  );

  const img = document.createElement("img");
  img.src = "/assets/upande_livestock/images/upande_mark.svg";
  img.alt = "Upande Livestock";
  img.setAttribute("style", "width:106px;height:auto;display:block");

  el.appendChild(img);
  document.body.appendChild(el);
}

/**
 * Leave for another document, showing the cover on the way.
 *
 * The navigation is deferred by a frame so the browser paints the cover before
 * it starts tearing this page down — assign location.href in the same tick and
 * the cover never appears.
 */
export function leaveTo(href: string): void {
  raiseSplash();
  window.requestAnimationFrame(() => {
    window.setTimeout(() => {
      window.location.href = href;
    }, 60);
  });
}
