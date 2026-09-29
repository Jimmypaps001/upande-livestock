import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Picker } from "@/components/ui/picker";
import type { BatchPlan, FeedLine } from "@/lib/feeding";
import { cn, fmt } from "@/lib/utils";

/**
 * What the run needs, against what the stores hold.
 *
 * Two units per line where they differ: the stock uom the store counts in
 * (hay: BALE) on top, and underneath it the recipe uom the mixer works to
 * (hay: kg). Both come from the server already resolved — nothing on this
 * page multiplies one into the other.
 *
 * FROM AND BATCH ARE PER LINE, when `stores` is given. A TMR draws its silage
 * from a pit, its concentrate from the mixing store and its hay from the hay
 * store; one dropdown for the whole run is a run the farm cannot post as it
 * actually works. Left alone, each line keeps the store the engine chose and
 * the batch the rule picks — which is shown underneath, because a rule nobody
 * can see is one nobody can correct.
 */
export function RequirementTable({
  lines,
  showConcentrateTag,
  stores,
  plans,
  lineStore,
  lineBatch,
  onStore,
  onBatch,
}: {
  lines: FeedLine[];
  showConcentrateTag?: boolean;
  /** Offering these turns From and Batch into pickers. */
  stores?: string[];
  plans?: Record<string, BatchPlan>;
  lineStore?: Record<string, string>;
  lineBatch?: Record<string, string>;
  onStore?: (itemCode: string, warehouse: string) => void;
  onBatch?: (itemCode: string, batchNo: string) => void;
}) {
  const pickable = !!stores && !!onStore;
  if (!lines?.length) return null;
  return (
    <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Item</TableHead>
            <TableHead className="text-right">Required</TableHead>
            <TableHead className="text-right">Available</TableHead>
            <TableHead className="text-right">Short</TableHead>
            <TableHead>From</TableHead>
            {pickable && <TableHead>Batch</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {lines.map((l) => {
            const short = Number(l.short_qty) || 0;
            const elsewhere = Number(l.available_elsewhere) || 0;
            return (
              <TableRow
                key={l.item_code}
                className={short > 0 ? "bg-[rgba(196,48,43,0.04)]" : undefined}
              >
                <TableCell className="font-medium text-[var(--sd-ink)]">
                  {l.item_name}
                  {showConcentrateTag && l.is_concentrate && (
                    <span className="ml-2 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--sd-muted)]">
                      Concentrate · {(l.concentrate_source || "").toLowerCase()}
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {fmt(l.required_qty)} {l.uom}
                  {l.recipe_uom && l.recipe_uom !== l.uom && (
                    <div className="text-[11px] text-[var(--sd-quiet)]">
                      {fmt(l.recipe_qty)} {l.recipe_uom}
                    </div>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {fmt(availableIn(l, lineStore?.[l.item_code]))}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right tabular-nums",
                    short > 0 && "font-semibold text-[var(--sd-sev-critical)]",
                  )}
                >
                  {short > 0 ? fmt(short) : "—"}
                </TableCell>
                <TableCell className="text-[12px] text-[var(--sd-muted)]">
                  {pickable ? (
                    <Picker
                      id={`f-from-${l.item_code}`}
                      value={lineStore?.[l.item_code] ?? ""}
                      onChange={(next) => onStore?.(l.item_code, next)}
                      options={[
                        {
                          value: "",
                          label: l.source_warehouse
                            ? `${l.source_warehouse} · ${fmt(l.available)} here`
                            : "As chosen",
                        },
                        // Every store, each saying what IT holds — choosing one
                        // blind is how a line is drawn from an empty shelf.
                        ...(stores ?? []).map((w) => ({
                          value: w,
                          label: `${w} · ${fmt(qtyIn(l, w))}`,
                        })),
                      ]}
                      label="Source store"
                      placeholder={l.source_warehouse || "As chosen"}
                    />
                  ) : (
                    l.source_warehouse || "—"
                  )}
                  {/* Where the rest of it is, by name. "+35,000 elsewhere"
                      tells an operator the feed exists and not where to go. */}
                  {othersHolding(l, lineStore?.[l.item_code]).length > 0 && (
                    <div className="text-[11px] text-[var(--sd-quiet)]">
                      also{" "}
                      {othersHolding(l, lineStore?.[l.item_code])
                        .map((w) => `${fmt(w.qty)} in ${w.warehouse}`)
                        .join(", ")}
                    </div>
                  )}
                  {othersHolding(l, lineStore?.[l.item_code]).length === 0 && elsewhere > 0 && (
                    <div className="text-[11px] text-[var(--sd-quiet)]">
                      +{fmt(elsewhere)} elsewhere
                    </div>
                  )}
                </TableCell>
                {pickable && (
                  <TableCell className="text-[12px] text-[var(--sd-muted)]">
                    {plans?.[l.item_code] && !plans[l.item_code].tracked ? (
                      // Not batch tracked, so nothing will ever ask it for a
                      // batch. Offering a picker here would invite a choice
                      // that cannot be honoured.
                      <span className="text-[var(--sd-quiet)]">not batched</span>
                    ) : (
                      <>
                    <Picker
                      id={`f-batch-${l.item_code}`}
                      value={lineBatch?.[l.item_code] ?? ""}
                      onChange={(next) => onBatch?.(l.item_code, next)}
                      options={[
                        { value: "", label: "Chosen by the rule" },
                        ...((plans?.[l.item_code]?.available ?? []).map((b) => ({
                          value: b.batch_no,
                          label: `${b.batch_no} · ${fmt(b.qty)} here${
                            b.expiry_date ? ` · expires ${b.expiry_date}` : ""
                          }`,
                        }))),
                      ]}
                      label="Batch"
                      placeholder="Chosen by the rule"
                    />
                    {/* The proposal in words: Picker drops an empty-valued
                        option, so this is the only place the rule's own choice
                        can be read before the run posts. */}
                    <div
                      className={
                        plans?.[l.item_code] && !plans[l.item_code].picks.length
                          ? "text-[11px] text-[var(--sd-sev-critical)]"
                          : "text-[11px] text-[var(--sd-quiet)]"
                      }
                    >
                      {lineBatch?.[l.item_code]
                        ? "Chosen by you"
                        : batchNote(plans?.[l.item_code])}
                    </div>
                      </>
                    )}
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}


/** What the rule proposes for one line, in a phrase. */
function batchNote(plan?: BatchPlan): string {
  if (!plan) return "Chosen by the rule";
  if (!plan.picks.length) return "Nothing in this store — the run will refuse";
  const head = plan.picks.map((p) => `${p.batch_no} (${fmt(p.qty)})`).join(" + ");
  return plan.short > 0 ? `${head} · short ${fmt(plan.short)}` : head;
}


/** What one store holds of this line, from the locations the server resolved. */
function qtyIn(line: FeedLine, warehouse: string): number {
  return (line.locations ?? []).find((w) => w.warehouse === warehouse)?.qty ?? 0;
}

/** What the chosen store holds — or, with none chosen, the engine's own. */
function availableIn(line: FeedLine, chosen?: string): number {
  return chosen ? qtyIn(line, chosen) : Number(line.available) || 0;
}

/** Stores holding it other than the one this line will actually be drawn from.
 *  Keyed on the operator's choice when there is one — otherwise picking a store
 *  leaves it listed under "also", as somewhere else to go. */
function othersHolding(
  line: FeedLine,
  chosen?: string,
): Array<{ warehouse: string; qty: number }> {
  const from = chosen || line.source_warehouse;
  return (line.locations ?? []).filter((w) => w.warehouse !== from);
}
