/**
 * The unread count behind the sidebar badge.
 *
 * POLLED, not pushed. The sibling app subscribes to a realtime event because it
 * runs inside pages that have already loaded Frappe's socketio bundle; this app
 * is served by a bare www template (www/livestock_app.html) that loads only its
 * own bundle, so there is no socket to listen on. The server still publishes the
 * event for the desk bell — see common/notifications.EVENT.
 *
 * Sixty seconds, and only while the tab is visible. These alerts are raised once
 * a night by a scheduler: a farm hand does not need to know within a second, and
 * a phone left open on a windowsill should not spend its battery asking.
 */

import { useCallback, useEffect, useState } from "react";
import { fetchUnreadCount } from "@/lib/notifications-api";

const POLL_MS = 60_000;

export function useUnreadNotifications(): {
  unread: number;
  refresh: () => Promise<void>;
  setUnread: (n: number) => void;
} {
  const [unread, setUnread] = useState(0);

  const refresh = useCallback(async () => {
    setUnread(await fetchUnreadCount());
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    const read = () => {
      if (document.hidden) return;
      fetchUnreadCount().then((n) => {
        if (!cancelled) setUnread(n);
      });
    };

    read();
    timer = setInterval(read, POLL_MS);
    // Coming back to the tab is the moment the number is most likely stale and
    // the moment somebody is actually looking at it.
    document.addEventListener("visibilitychange", read);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      document.removeEventListener("visibilitychange", read);
    };
  }, []);

  return { unread, refresh, setUnread };
}
