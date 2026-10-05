import { useEffect, useState } from "react";
import { call, isError, type Envelope } from "@/lib/frappe";

/**
 * Today as the server counts it, and whether a record may be dated earlier.
 *
 * The browser's clock is not the farm's: in another time zone its "today" is
 * the server's yesterday, and an untouched date was refused as backdated. Asked
 * once per page load and shared by every date field on it.
 */
export type PostingDay = { today: string; backdating_open: boolean };

let pending: Promise<Envelope<PostingDay & { ok: boolean }>> | null = null;

export function fetchPostingDay(): Promise<Envelope<PostingDay & { ok: boolean }>> {
  if (!pending) {
    pending = call("upande_livestock.serverscripts.settings.posting_day.posting_day");
    // A failure is not cached, so the next field asks again.
    pending.then((r) => {
      if (isError(r)) pending = null;
    });
  }
  return pending;
}

/** Forget the answer — after Backdating Open is changed on the Settings page. */
export function forgetPostingDay(): void {
  pending = null;
}

export function usePostingDay(): PostingDay | null {
  const [day, setDay] = useState<PostingDay | null>(null);
  useEffect(() => {
    let live = true;
    void fetchPostingDay().then((r) => {
      if (live && !isError(r)) setDay({ today: r.today, backdating_open: r.backdating_open });
    });
    return () => {
      live = false;
    };
  }, []);
  return day;
}
