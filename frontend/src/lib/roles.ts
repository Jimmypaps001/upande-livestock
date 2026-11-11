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

/** The screens a nutritionist works in. Feed Design first: it is where they land. */
export const NUTRITIONIST_VIEWS: readonly View[] = [
  "feed-design",
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
