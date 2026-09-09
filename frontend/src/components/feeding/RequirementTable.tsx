import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { FeedLine } from "@/lib/feeding";
import { cn, fmt } from "@/lib/utils";

/**
 * What the run needs, against what the stores hold.
 *
 * Two units per line where they differ: the stock uom the store counts in
 * (hay: BALE) on top, and underneath it the recipe uom the mixer works to
 * (hay: kg). Both come from the server already resolved — nothing on this
 * page multiplies one into the other.
 */
export function RequirementTable({
  lines,
  showConcentrateTag,
}: {
  lines: FeedLine[];
  showConcentrateTag?: boolean;
}) {
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
                <TableCell className="text-right tabular-nums">{fmt(l.available)}</TableCell>
                <TableCell
                  className={cn(
                    "text-right tabular-nums",
                    short > 0 && "font-semibold text-[var(--sd-sev-critical)]",
                  )}
                >
                  {short > 0 ? fmt(short) : "—"}
                </TableCell>
                <TableCell className="text-[12px] text-[var(--sd-muted)]">
                  {l.source_warehouse || "—"}
                  {elsewhere > 0 && (
                    <div className="text-[11px] text-[var(--sd-quiet)]">
                      +{fmt(elsewhere)} elsewhere
                    </div>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
