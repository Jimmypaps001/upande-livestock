import { bootstrap } from "@/lib/frappe";
import type { View } from "@/lib/router";

/**
 * The nutritionist: keeps the feed library's nutrient figures and balances the
 * herds' rations and concentrates. Mirrors NUTRITIONIST_ROLE in
 * serverscripts/common/envelope.py.
 *
 * The server is what refuses — this only keeps a user who holds nothing but
 * this role from being shown screens and buttons that would answer "not
 * permitted". Anyone who also holds a farm role sees the whole app as before.
 */
export const NUTRITIONIST_ROLE = "Livestock Nutritionist";

const WIDER_ROLES = [
  "Livestock Manager",
  "Livestock Vet",
  "Livestock Breeder",
  "Livestock Attendant",
  "Livestock Stores",
  "System Manager",
  "Administrator",
];

/** The screens a nutritionist works in. The Ration Editor first: it is where they land. */
export const NUTRITIONIST_VIEWS: readonly View[] = [
  "ration-editor",
  "rations",
  "concentrate",
  "stock",
];

/** True when the user holds the nutritionist role and no wider farm role. */
export function nutritionistOnly(roles: string[] = bootstrap().roles): boolean {
  return roles.includes(NUTRITIONIST_ROLE) && !roles.some((r) => WIDER_ROLES.includes(r));
}

/** May this user see `view`? Everyone may, except a nutritionist-only user. */
export function viewAllowed(view: View, roles: string[] = bootstrap().roles): boolean {
  return !nutritionistOnly(roles) || NUTRITIONIST_VIEWS.includes(view);
}

/** Mixing and issuing feed moves stock, which the nutritionist does not do. */
export function canMix(roles: string[] = bootstrap().roles): boolean {
  return !nutritionistOnly(roles);
}

/**
 * Does this farm have a concentrate stage at all?
 *
 * ONE RULE: concentrate is in use when at least one herd eats a pre-made one.
 * A herd's Concentrate setting (Herds) decides for that herd; a herd left on
 * "Farm default" follows Livestock Settings > Pre-manufacture Concentrate. So
 * the farm switch on with every herd on its default shows the Concentrate
 * window; the switch off with the shoat groups on "Pre-manufacture" still
 * shows it, because their batch has to be mixed somewhere. A farm with no
 * herds answers with the switch.
 *
 * The server decides it (`_concentrate.any_herd_premanufactures`) and sends
 * the answer in the page's bootstrap as `premanufacture_concentrate`; this
 * only reads it, so the sidebar, the route and the server cannot disagree.
 */
export function concentratesInUse(on: boolean = bootstrap().premanufacture_concentrate): boolean {
  return on;
}

/**
 * The event types each record page records. A farm can switch an event off
 * (Settings → Events; the server's `common/event_types`), and then the page
 * that records it leaves the menu and its route sends you elsewhere. A page
 * recording several types (Husbandry) stays while any of them is on — the
 * page itself only offers the ones that are. Pages not listed record no event
 * type of their own and are never hidden for one.
 */
export const VIEW_EVENTS: Partial<Record<View, readonly string[]>> = {
  movement: ["Movement"],
  calving: ["Calving"],
  heat: ["Heat Detection"],
  service: ["Service"],
  diagnosis: ["Pregnancy Diagnosis"],
  abortion: ["Abortion"],
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

/** May `view` be opened on this farm by this user? The role rule, the
 *  Concentrate window only where concentrate is in use, and a record page only
 *  while its event is switched on. */
export function viewOpen(
  view: View,
  roles: string[] = bootstrap().roles,
  inUse: boolean = concentratesInUse(),
  disabled: readonly string[] = bootstrap().disabled_events,
): boolean {
  if (view === "concentrate" && !inUse) return false;
  if (!viewEventsOn(view, disabled)) return false;
  return viewAllowed(view, roles);
}

/** Where to send someone who opened a screen they may not: the nutritionist
 *  to the Ration Editor, everyone else to Feeding. */
export function landingView(roles: string[] = bootstrap().roles): View {
  return nutritionistOnly(roles) ? NUTRITIONIST_VIEWS[0] : "feeding";
}
