import { useCallback, useEffect, useState } from "react";

import { isError } from "@/lib/frappe";
import { searchEmployees } from "@/lib/people";

/**
 * Who is recording this.
 *
 * EVERY LIVESTOCK EVENT HAS TO SAY WHO MADE IT — the server refuses one that
 * does not, by name. The options endpoints answer with the Employee linked to
 * the signed-in user, which on this farm is often nobody: the yard runs off one
 * tablet on a shared login, and Administrator has no Employee at all.
 *
 * WHETHER TO ASK IS NOT THE SAME QUESTION AS WHAT THE ANSWER IS, and conflating
 * them is a bug I shipped: `needed` was `!operator`, so the field asking for an
 * operator unmounted the moment somebody typed the first letter into it. The
 * two are separate now — `mustAsk` is settled once, when the server says
 * whether it knows who you are, and never changes because of what is in the
 * box.
 *
 * Asked ONCE and remembered, rather than on every page: a herdsman who has told
 * the app who he is should not be asked again walking from the movement screen
 * to the calving screen. Kept in `localStorage` deliberately — it is a
 * convenience for this device, not a claim about identity. The server still
 * checks what the SESSION may do; this only fills in a field somebody would
 * otherwise type forty times a day, and a wrong value shows up on the event as
 * the wrong name rather than granting anybody anything.
 */
const KEY = "upande.livestock.operator";

function remembered(): string {
  try {
    return window.localStorage.getItem(KEY) || "";
  } catch {
    // Private windows, cleared site data, a locked-down kiosk browser. The
    // field simply starts empty, which is the same as never having answered.
    return "";
  }
}

export function useOperator(fromServer?: string | null) {
  const [operator, set] = useState<string>(() => remembered());
  // Null until the server has answered; the screens must not decide whether to
  // ask before they know.
  const [linked, setLinked] = useState<string | null>(fromServer ?? null);
  const [asked, setAsked] = useState(false);

  useEffect(() => {
    if (fromServer) {
      setLinked(fromServer);
      set(fromServer);
      setAsked(true);
    }
  }, [fromServer]);

  // A page that gets no employee from its own options endpoint still has to
  // know whether the signed-in user has one, so it asks the one endpoint that
  // can say. Without this, every page on a properly linked login would still
  // put a picker in front of somebody the app could already identify.
  useEffect(() => {
    if (fromServer || asked) return;
    let live = true;
    void searchEmployees("").then((r) => {
      if (!live || isError(r)) return;
      setAsked(true);
      if (r.mine) {
        setLinked(r.mine);
        set((current) => current || r.mine!);
      }
    });
    return () => {
      live = false;
    };
  }, [fromServer, asked]);

  const setOperator = useCallback((next: string) => {
    set(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* nothing to do; the value still works for this page. */
    }
  }, []);

  return {
    operator,
    setOperator,
    /** Show the picker: the signed-in user has no Employee of their own. */
    mustAsk: asked && !linked,
    /** Block the save: we still have nobody to name. */
    needed: !operator.trim(),
    /** What to send. Undefined rather than "" so the server's own fallback
     *  still applies for a user who does have an Employee. */
    value: operator.trim() || undefined,
  };
}
