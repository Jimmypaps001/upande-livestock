import { can } from "@/lib/can";
import { bootstrap, type Capabilities } from "@/lib/frappe";
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

/**
 * What a screen needs of the user, read off the guards of the endpoints it
 * calls (guard_read: read; guard: create; guard_stock: a flag). A screen the
 * user fails is left out of the menu and its route sends them home — hidden,
 * not shown and refused. Quality-only users are limited by LIMITED_ROLES above.
 */
type Flag = Parameters<typeof can.flag>[0];
type Need = {
  read?: string[];
  create?: string[];
  flag?: Flag;
  /** Enough that ANY one of these holds (a page with two kinds of work on it). */
  any?: Array<{ create?: string; flag?: Flag }>;
};
const EVENT = { read: ["Livestock Event"], create: ["Livestock Event"] };
export const VIEW_NEEDS: Partial<Record<View, Need>> = {
  dashboard: { read: ["Animal"] },
  animals: { read: ["Animal"] },
  events: { read: ["Animal"] },
  production: { read: ["Animal"] },
  reports: { read: ["Animal"] },
  health: { read: ["Livestock Health Case"] },
  transactions: { flag: "post_draft" },
  // Mixing and issuing needs the stock roles; the day sheet needs the actuals.
  feeding: { read: ["Herds"], any: [{ flag: "stock" }, { create: "Livestock Feed Actual" }] },
  concentrate: { read: ["BOM"] },
  stock: { read: ["Item"] },
  "feed-report": { read: ["Herds", "Animal"] },
  rations: { read: ["BOM"] },
  "ration-editor": { read: ["BOM"], create: ["BOM"] },
  procurement: { read: ["Item"], flag: "stock" },
  milking: { read: ["Milk Recording"], create: ["Milk Recording"] },
  quality: { read: ["Milk Quality Test"], flag: "quality" },
  "feed-quality": { read: ["Milk Recording"], flag: "quality" },
  movement: EVENT,
  "drying-off": EVENT,
  calving: EVENT,
  heat: EVENT,
  service: EVENT,
  diagnosis: EVENT,
  husbandry: EVENT,
  abortion: EVENT,
  weight: { read: ["Livestock Weight Record"], create: ["Livestock Weight Record"] },
  "check-up": { read: ["Livestock Health Case"], create: ["Livestock Diagnosis"] },
  treatment: { read: ["Livestock Health Case"], create: ["Livestock Health Case"] },
  "health-case": { read: ["Livestock Health Case"] },
  herds: { read: ["Herds"], any: [{ create: "Herds" }, { create: "Animal" }] },
  culling: { read: ["Livestock Disposal"] },
  vets: { read: ["Livestock Vet"] },
  sires: { read: ["Livestock Sire"], flag: "manage_sires" },
  claims: { read: ["Livestock Loss"] },
  "loss-scenarios": { read: ["Livestock Loss Scenario"] },
  settings: { read: ["Livestock Settings"] },
  notifications: { read: ["Notification Log"] },
};

/** Does the user's capability map cover everything `view` needs? */
export function viewPermitted(view: View, from: Capabilities | null = bootstrap().can): boolean {
  const need = VIEW_NEEDS[view];
  // No map (a stale page): nothing is hidden for permissions; the server refuses.
  if (!need || !from) return true;
  return (
    (need.read ?? []).every((d) => can.read(d, from)) &&
    (need.create ?? []).every((d) => can.create(d, from)) &&
    (!need.flag || can.flag(need.flag, from)) &&
    (!need.any ||
      need.any.some((a) => (a.create ? can.create(a.create, from) : false) || (a.flag ? can.flag(a.flag, from) : false)))
  );
}

/** May this user see `view`? Not a user limited to other screens, and not one
 *  whose permissions do not cover what the screen reads and records. */
export function viewAllowed(
  view: View,
  roles: string[] = bootstrap().roles,
  from: Capabilities | null = bootstrap().can,
): boolean {
  const limited = limitedViews(roles);
  if (limited !== null && !limited.includes(view)) return false;
  return viewPermitted(view, from);
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
  from: Capabilities | null = bootstrap().can,
): boolean {
  return viewEventsOn(view, disabled) && viewAllowed(view, roles, from);
}

/** Where a user starts, and where one who opened a screen they may not is sent:
 *  a limited user's first screen, everyone else Feeding, or the Dashboard on a
 *  farm that switched Feeding off (Feeding would only send them on again, round
 *  and round). */
export function landingView(
  roles: string[] = bootstrap().roles,
  disabled: readonly string[] = bootstrap().disabled_events,
  from: Capabilities | null = bootstrap().can,
): View {
  const limited = limitedViews(roles)?.[0];
  if (limited) return limited;
  // The first screen the user may open, in the order of the menu: Feeding is
  // the farm's home, but a user who cannot read herds lands on what they can.
  const open = (v: View) => viewOpen(v, roles, disabled, from);
  return LANDING.find(open) ?? "notifications";
}

const LANDING: readonly View[] = ["feeding", "dashboard", "animals", "milking", "quality", "health", "vets", "settings", "notifications"];

/**
 * May this user record on behalf of another Employee (the operator picker)?
 * Only a System Manager or Administrator; the server enforces the same rule
 * (`common/employee.acting_employee`) and gives everyone else their own.
 */
export function canChooseOperator(
  roles: string[] = bootstrap().roles,
  user: string = bootstrap().user,
): boolean {
  const from = bootstrap().can;
  if (from) return from.operator;
  return user === "Administrator" || roles.includes("System Manager");
}

/** Mixing and issuing feed moves stock: the farm's stores and manager roles (the server decides). */
export function canMix(roles: string[] = bootstrap().roles): boolean {
  return can.flag("stock", bootstrap().can, roles);
}
