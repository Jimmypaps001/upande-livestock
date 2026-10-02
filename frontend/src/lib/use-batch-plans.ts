import { useEffect, useRef, useState } from "react";

import { eventBatches, type BatchPlan } from "@/lib/feeding";
import { isError } from "@/lib/frappe";

/**
 * The one key a plan is stored and read under. A plan is an answer about an
 * item in a STORE: the same drug in two stores holds different batches, and
 * one keyed by the item alone offers one store's batches against the other's
 * issue. The builder and the reader both come through here so they cannot drift.
 */
export const planKey = (item: string, store: string) => `${item}\u0000${store}`;

/**
 * What the batch rule would take for each row of an Items table, asked again
 * whenever an item or a store changes. (Not the quantity: only `available`
 * and `tracked` are shown, and neither depends on it.)
 *
 * Only rows with an item AND a store are asked about, and nothing is sent when
 * there are none. A plan that has not arrived is absent from the map — the
 * table renders nothing for it, because "not batched" is a claim only an
 * answer may make. Each answer REPLACES the map, and a failed or empty ask
 * clears it: showing nothing beats showing a stale answer.
 */
export function useBatchPlans(
  rows: Array<{ item: string; store: string; qty: string }>,
): Record<string, BatchPlan> {
  const [plans, setPlans] = useState<Record<string, BatchPlan>>({});

  const want = rows
    .filter((r) => r.item && r.store)
    .map((r) => ({ item_code: r.item, qty: Number(r.qty) || 0, warehouse: r.store }));
  const latest = useRef(want);
  latest.current = want;
  const key = JSON.stringify(want.map((w) => [w.item_code, w.warehouse]));

  useEffect(() => {
    const lines = latest.current;
    if (!lines.length) {
      setPlans({});
      return;
    }
    let live = true;
    void eventBatches(lines).then((r) => {
      if (!live) return;
      if (isError(r)) {
        setPlans({});
        return;
      }
      // `lines` is the server's to send and ours to survive without: a success
      // envelope that carries none means no plan for any row, which is the same
      // answer as an empty list. Reading `.map` off it unguarded threw inside
      // the promise, so it surfaced as an unhandled rejection the suite counted
      // and no test failed on.
      setPlans(Object.fromEntries((r.lines ?? []).map((p) => [planKey(p.item_code, p.warehouse), p])));
    });
    return () => {
      live = false;
    };
  }, [key]);

  return plans;
}
