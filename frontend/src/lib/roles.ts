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

/** May `view` be opened on this farm by this user? The role rule, plus the
 *  Concentrate window only where concentrate is in use. */
export function viewOpen(
  view: View,
  roles: string[] = bootstrap().roles,
  inUse: boolean = concentratesInUse(),
): boolean {
  if (view === "concentrate" && !inUse) return false;
  return viewAllowed(view, roles);
}

/** Where to send someone who opened a screen they may not: the nutritionist
 *  to the Ration Editor, everyone else to Feeding. */
export function landingView(roles: string[] = bootstrap().roles): View {
  return nutritionistOnly(roles) ? NUTRITIONIST_VIEWS[0] : "feeding";
}
