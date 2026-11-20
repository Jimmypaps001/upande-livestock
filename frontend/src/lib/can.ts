import { bootstrap, type Capabilities } from "@/lib/frappe";

/**
 * What the signed-in user may do — the one place the desk asks.
 *
 * The rule: if someone should not access something, take it out of their view.
 * The server decides (serverscripts/common/capabilities.py builds the `can` map
 * from the same permissions its endpoints check) and ships it in the page's
 * bootstrap; components ask `can.read("Animal")`, `can.flag("insure")` and never
 * name a role themselves.
 *
 * A page without the map (a stale cache from before it existed) falls back to
 * the roles: the few role-gated actions by the same role lists the server uses,
 * everything else open — the server still refuses, as it always did.
 */

type Flag = Exclude<keyof Capabilities, "read" | "create" | "write">;

const ALL = ["System Manager", "Administrator"];

/** Role lists mirrored from the server, for the stale-page fallback only; null = open (the server still refuses). */
const FLAG_ROLES: Record<Flag, readonly string[] | null> = {
  stock: ["Livestock Stores", "Livestock Manager", ...ALL],
  post_draft: null,
  override_feed: null,
  insure: ["Accounts Manager", "Accounts User", ...ALL],
  accounts: null,
  appreciate: null,
  cull_vet: null,
  cull_manager: null,
  operator: ALL,
};

function map(): Capabilities | null {
  return bootstrap().can;
}

export const can = {
  /** May the user read this doctype (open a page that lists it)? */
  read(doctype: string, from: Capabilities | null = map()): boolean {
    return from ? !!from.read?.[doctype] : true;
  },
  /** May the user create this doctype (record what a page records)? */
  create(doctype: string, from: Capabilities | null = map()): boolean {
    return from ? !!from.create?.[doctype] : true;
  },
  /** May the user change an existing one (sign a case, settle a claim)? */
  write(doctype: string, from: Capabilities | null = map()): boolean {
    return from ? !!from.write?.[doctype] : true;
  },
  /** A role-gated action: insure, accounts, override_feed, stock, ... */
  flag(name: Flag, from: Capabilities | null = map(), roles: string[] = bootstrap().roles): boolean {
    if (from) return !!from[name];
    const wanted = FLAG_ROLES[name];
    return wanted === null || roles.some((r) => wanted.includes(r));
  },
};
