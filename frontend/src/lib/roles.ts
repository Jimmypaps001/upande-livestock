import { bootstrap } from "@/lib/frappe";
import type { View } from "@/lib/router";

/**
 * Roles that see only part of the app.
 *
 * The server is what refuses — this only keeps a user who holds nothing but a
 * limited role from being shown screens that would answer "not permitted", and
 * sends them to the first screen of their own. Anyone who also holds a wider
 * farm role sees the whole app as before.
 *
 * A limited role is one line in LIMITED_ROLES: the role and the screens it
 * works in, the first being where it lands. Mirrors QUALITY_ROLE in
 * serverscripts/common/envelope.py.
 */

/** The lab: files bulk tank quality against milkings and reads the quality pages. */
export const QUALITY_ROLE = "Livestock Quality";

/** The screens the lab reaches: Quality first (where it lands), then Feed vs quality. */
export const QUALITY_VIEWS: readonly View[] = ["quality", "feed-quality"];

export const LIMITED_ROLES: ReadonlyArray<{ role: string; views: readonly View[] }> = [
  { role: QUALITY_ROLE, views: QUALITY_VIEWS },
];

/** Any of these means the user works on the farm at large, so nothing is hidden. */
const WIDER_ROLES = [
  "Livestock Manager",
  "Livestock Vet",
  "Livestock Breeder",
  "Livestock Attendant",
  "Livestock Milker",
  "Livestock Stores",
  "System Manager",
  "Administrator",
];

/**
 * The screens a limited user may open (those of every limited role they hold,
 * in the order the roles are listed), or null when nothing is limited: they
 * hold no limited role, or a wider farm role as well.
 */
export function limitedViews(roles: string[] = bootstrap().roles): readonly View[] | null {
  if (roles.some((r) => WIDER_ROLES.includes(r))) return null;
  const held = LIMITED_ROLES.filter((l) => roles.includes(l.role));
  if (held.length === 0) return null;
  return [...new Set(held.flatMap((l) => l.views))];
}

/** True when the user holds the quality role and no wider farm role. */
export function qualityOnly(roles: string[] = bootstrap().roles): boolean {
  return roles.includes(QUALITY_ROLE) && limitedViews(roles) !== null;
}

/** May this user see `view`? Everyone may, except a user limited to other screens. */
export function viewAllowed(view: View, roles: string[] = bootstrap().roles): boolean {
  const limited = limitedViews(roles);
  return limited === null || limited.includes(view);
}

/**
 * The event types each record page records. A farm can switch an event off
 * (Settings → Events; the server's `common/event_types`), and then the page
 * that records it leaves the menu and its route sends you elsewhere. A page
 * recording several types (Husbandry) stays while any of them is on; the page
 * itself only offers the ones that are. Pages not listed record no event type
 * of their own and are never hidden for one.
 */
export const VIEW_EVENTS: Partial<Record<View, readonly string[]>> = {
  // Feeding issues feed (a herd's mix, a manual mix), and every issue is a
  // Feeding event. The Ration Editor, the rations and the Concentrate window
  // design and mix but feed no herd, so they stay.
  feeding: ["Feeding"],
  movement: ["Movement"],
  calving: ["Calving"],
  heat: ["Heat Detection"],
  service: ["Service"],
  diagnosis: ["Pregnancy Diagnosis"],
  abortion: ["Abortion"],
  "drying-off": ["Drying Off"],
  weight: ["Weight Recording"],
  "check-up": ["Check Up"],
  treatment: ["Treatment"],
  "health-case": ["Health Case"],
  husbandry: ["Vaccination", "Deworming", "Dehorning", "Hoof Trimming"],
};

/** Does the farm record `eventType`? Everything is on unless switched off. */
export function eventEnabled(
  eventType: string,
  disabled: readonly string[] = bootstrap().disabled_events,
): boolean {
  return !disabled.includes(eventType);
}

/** Is the event behind `view` switched on (any of them, for a page of several)? */
export function viewEventsOn(
  view: View,
  disabled: readonly string[] = bootstrap().disabled_events,
): boolean {
  const events = VIEW_EVENTS[view];
  return !events || events.some((e) => eventEnabled(e, disabled));
}

/** May `view` be opened on this farm by this user? The role rule, and a record
 *  page only while its event is switched on. */
export function viewOpen(
  view: View,
  roles: string[] = bootstrap().roles,
  disabled: readonly string[] = bootstrap().disabled_events,
): boolean {
  return viewEventsOn(view, disabled) && viewAllowed(view, roles);
}

/** Where a user starts, and where one who opened a screen they may not is sent:
 *  a limited user's first screen, everyone else Feeding, or the Dashboard on a
 *  farm that switched Feeding off (Feeding would only send them on again, round
 *  and round). */
export function landingView(
  roles: string[] = bootstrap().roles,
  disabled: readonly string[] = bootstrap().disabled_events,
): View {
  const limited = limitedViews(roles)?.[0];
  if (limited) return limited;
  return viewEventsOn("feeding", disabled) ? "feeding" : "dashboard";
}
