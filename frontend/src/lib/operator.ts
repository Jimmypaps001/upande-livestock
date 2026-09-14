import { useCallback, useEffect, useState } from "react";

/**
 * Who is recording this.
 *
 * EVERY LIVESTOCK EVENT HAS TO SAY WHO MADE IT — the server refuses one that
 * does not, by name: "Operator(technician) is mandatory for a hand-entered
 * Livestock Event". The options endpoints answer with the Employee linked to
 * the signed-in user, which on this farm is usually nobody: the yard runs off
 * one tablet on a shared login, and Administrator has no Employee at all.
 *
 * Asked ONCE and remembered, rather than on every page. A herdsman who has told
 * the app who he is should not be asked again when he walks from the movement
 * screen to the calving screen, and a page that asked every time would be a
 * page people learn to click past.
 *
 * Kept in `localStorage` deliberately: it is a convenience for this device, not
 * a claim about identity. The server still checks what the *session* may do —
 * this only fills in a field the operator would otherwise type forty times a
 * day, and a wrong value shows up on the event as somebody else's name rather
 * than granting anybody anything.
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

  // The Employee the server resolved wins over anything remembered here: it is
  // the one answer that came from a login rather than from a box.
  useEffect(() => {
    if (fromServer) set(fromServer);
  }, [fromServer]);

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
    /** Whether the screen has to ask. */
    needed: !operator.trim(),
    /** What to send. Undefined rather than "" so the server's own fallback
     *  still applies for a user who does have an Employee. */
    value: operator.trim() || undefined,
  };
}
