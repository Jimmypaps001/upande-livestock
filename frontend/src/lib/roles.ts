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

/** Where a user starts, and where one who opened a screen they may not is sent:
 *  a limited user's first screen, everyone else Feeding. */
export function landingView(roles: string[] = bootstrap().roles): View {
  return limitedViews(roles)?.[0] ?? "feeding";
}
