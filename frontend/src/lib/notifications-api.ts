/**
 * In-app notifications.
 *
 * Backed by Frappe's Notification Log. Every row this app shows is anchored to
 * the `Livestock Alert` that earned it, which is what keeps an upande_scp
 * notification — the same site runs both apps — out of this list and out of the
 * sidebar badge. The category is derived server-side from the alert's kind; see
 * serverscripts/common/notifications.py.
 *
 * Every endpoint resolves the user from the session. None of them accept a
 * `for_user`, deliberately, so one user cannot read or clear another's.
 */

import { call, isError } from "./frappe";

export type LivestockCategory = "movement" | "breeding" | "feed";

export type AlertKind =
  | "Bull Cull Due"
  | "Move Due"
  | "Move Overdue"
  | "Cow Open Too Long"
  | "Calving Due"
  | "Pregnancy Check Overdue"
  // The two kinds that are not about an animal. A concentrate running out
  // stops every herd that eats it, so it names an `item` where the rest name
  // an `animal`.
  | "Concentrate Low"
  | "Concentrate Out";

export interface LivestockNotification {
  name: string;
  subject: string;
  email_content?: string;
  read: 0 | 1;
  creation: string;
  document_type?: string | null;
  document_name?: string | null;
  alert_kind?: AlertKind | null;
  severity?: "Due" | "Overdue" | null;
  animal?: string | null;
  herd?: string | null;
  item?: string | null;
  alert_status?: string | null;
  category?: LivestockCategory | null;
}

const BASE = "upande_livestock.serverscripts.notifications";

export const CATEGORY_LABEL: Record<LivestockCategory, string> = {
  movement: "Movement",
  breeding: "Breeding",
  feed: "Feed",
};

export async function fetchNotifications(
  opts: {
    category?: LivestockCategory | "";
    unreadOnly?: boolean;
    limit?: number;
    offset?: number;
  } = {},
): Promise<{ notifications: LivestockNotification[]; unread: number; error?: string }> {
  const r = await call<{ notifications: LivestockNotification[]; unread: number }>(
    `${BASE}.list_notifications.list_notifications`,
    {
      category: opts.category || undefined,
      unread_only: opts.unreadOnly ? 1 : 0,
      limit: opts.limit ?? 50,
      offset: opts.offset ?? 0,
    },
  );
  if (isError(r)) return { notifications: [], unread: 0, error: r.error };
  return { notifications: r.notifications ?? [], unread: r.unread ?? 0 };
}

export async function fetchUnreadCount(): Promise<number> {
  const r = await call<{ unread: number }>(`${BASE}.unread_count.unread_count`, {});
  // A badge is never worth an error message. A failed count reads as zero and
  // the next poll corrects it.
  return isError(r) ? 0 : Number(r.unread) || 0;
}

export async function markRead(
  arg: { names?: string[]; all?: boolean } = {},
): Promise<number> {
  const r = await call<{ unread: number }>(`${BASE}.mark_read.mark_read`, {
    names: arg.names ? JSON.stringify(arg.names) : undefined,
    all: arg.all ? 1 : 0,
  });
  // Re-ask rather than guess: the server owns the count.
  return isError(r) ? await fetchUnreadCount() : (r.unread ?? 0);
}

/** "3m ago" / "2h ago" / "5 Aug" — compact enough for a list row. */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const t = new Date((iso || "").replace(" ", "T"));
  if (Number.isNaN(t.getTime())) return "";
  const secs = Math.max(0, Math.floor((now.getTime() - t.getTime()) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return t.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
