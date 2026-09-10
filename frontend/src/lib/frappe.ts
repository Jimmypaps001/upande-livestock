/**
 * The one way this app talks to Frappe.
 *
 * Two things it deliberately does NOT do:
 *
 *  * It does not translate the server's words. Every livestock endpoint returns
 *    `{"error": "..."}` in the body rather than raising (see
 *    serverscripts/common/envelope.py: `run`), and those messages are written
 *    for a farm worker — a refused backdated feed run names each short item and
 *    the earliest date that would work. Callers surface `error` unchanged.
 *  * It does not convert units. Quantities cross this boundary in whatever unit
 *    the server named; see lib/feeding.ts.
 */

export interface LivestockBootstrap {
  user: string;
  full_name: string;
  user_image: string;
  site_name: string;
  roles: string[];
}

declare global {
  interface Window {
    LIVESTOCK?: {
      csrf_token?: string;
      bootstrap?: Partial<LivestockBootstrap> & Record<string, unknown>;
    };
    csrf_token?: string;
  }
}

function csrf(): string {
  return window.LIVESTOCK?.csrf_token || window.csrf_token || "";
}

export function bootstrap(): LivestockBootstrap {
  const raw = window.LIVESTOCK?.bootstrap || {};
  return {
    user: typeof raw.user === "string" ? raw.user : "",
    full_name: typeof raw.full_name === "string" ? raw.full_name : "",
    user_image: typeof raw.user_image === "string" ? raw.user_image : "",
    site_name: typeof raw.site_name === "string" ? raw.site_name : "",
    roles: Array.isArray(raw.roles) ? (raw.roles as string[]) : [],
  };
}

/** Anything an endpoint may answer with. `error` is the refusal channel. */
export type Envelope<T> = (T & { ok?: boolean; error?: string }) | { error: string };

export function isError<T>(r: Envelope<T> | null | undefined): r is { error: string } {
  return !!r && typeof (r as { error?: unknown }).error === "string" && !!(r as { error: string }).error;
}

/**
 * POST a whitelisted method and hand back its `message`.
 *
 * A transport failure is folded into the same `{error}` shape the endpoints
 * use, so every caller has exactly one thing to check. Nothing here throws.
 */
export async function call<T>(
  method: string,
  args: Record<string, unknown> = {},
): Promise<Envelope<T>> {
  try {
    const res = await fetch(`/api/method/${method}`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": csrf(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(args),
    });
    const text = await res.text();
    let body: unknown = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = null;
    }
    const message =
      body && typeof body === "object" && "message" in body
        ? (body as { message: unknown }).message
        : null;
    if (message && typeof message === "object") return message as Envelope<T>;
    if (!res.ok) {
      // A raise that escaped the envelope (a 403 from the framework itself,
      // a stale CSRF token on a page left open overnight). Say which.
      const exc =
        body && typeof body === "object" && "exception" in body
          ? String((body as { exception: unknown }).exception)
          : "";
      if (res.status === 403 || res.status === 401) {
        return { error: exc || "Your session has expired. Reload the page and sign in again." };
      }
      return { error: exc || res.statusText || "The server refused that request." };
    }
    return { error: "No response from the server." };
  } catch {
    return { error: "Network error — the request did not reach the server." };
  }
}

/**
 * Link-field search, through the framework's own autosuggest endpoint.
 *
 * `frappe.desk.search.search_link` is what every desk Link field calls, and it
 * applies the same permission check: a user who may not list Warehouse gets an
 * empty list, not somebody else's warehouses. Using it here means the settings
 * page offers only records that exist — the alternative, a text box, is how a
 * milk warehouse ends up spelled two ways and a month of postings lands
 * nowhere.
 *
 * Returns `null` — not `[]` — when the call itself failed, so a picker can say
 * "could not search" instead of "no matches", which are different problems.
 */
export async function searchLink(
  doctype: string,
  term: string,
  pageLength = 20,
): Promise<Array<{ value: string; description: string; label?: string }> | null> {
  try {
    const res = await fetch("/api/method/frappe.desk.search.search_link", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": csrf(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ doctype, txt: term, page_length: pageLength }),
    });
    if (!res.ok) return null;
    const body = await res.json();
    const rows = body?.message;
    return Array.isArray(rows) ? rows : null;
  } catch {
    return null;
  }
}

/** Item-master search, through the same whitelisted read every desk Link field
 *  uses. Every livestock role already reads the item master, so this needs no
 *  endpoint of its own. */
export async function searchItems(
  term: string,
): Promise<Array<{ name: string; item_name: string; stock_uom: string }>> {
  try {
    const res = await fetch("/api/method/frappe.client.get_list", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": csrf(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({
        doctype: "Item",
        filters: [["item_name", "like", `%${term}%`]],
        fields: ["name", "item_name", "stock_uom"],
        limit_page_length: 20,
        order_by: "item_name asc",
      }),
    });
    const body = await res.json();
    return body?.message || [];
  } catch {
    return [];
  }
}
