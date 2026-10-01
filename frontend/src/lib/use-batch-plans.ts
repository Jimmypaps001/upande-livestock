import { useEffect, useState } from "react";

import { eventBatches, type BatchPlan } from "@/lib/feeding";
import { isError } from "@/lib/frappe";

/**
 * What the batch rule would take for each row of an Items table, asked again
 * whenever an item, a store or a quantity changes.
 *
 * Only rows with an item AND a store are asked about, and nothing is sent when
 * there are none. A plan that has not arrived is simply absent from the map —
 * the table renders nothing for it, because "not batched" is a claim only an
 * answer may make. Keyed by item code, as the table reads it.
 */
export function useBatchPlans(
  rows: Array<{ item: string; store: string; qty: string }>,
): Record<string, BatchPlan> {
  const [plans, setPlans] = useState<Record<string, BatchPlan>>({});

  const want = rows
    .filter((r) => r.item && r.store)
    .map((r) => ({ item_code: r.item, qty: Number(r.qty) || 0, warehouse: r.store }));
  const key = JSON.stringify(want);

  useEffect(() => {
    const lines = JSON.parse(key) as typeof want;
    if (!lines.length) return;
    let live = true;
    void eventBatches(lines).then((r) => {
      if (!live || isError(r)) return;
      setPlans(Object.fromEntries(r.lines.map((p) => [p.item_code, p])));
    });
    return () => {
      live = false;
    };
  }, [key]);

  return plans;
}
