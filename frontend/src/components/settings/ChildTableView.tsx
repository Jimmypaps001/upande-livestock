import { Lock } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SettingsTable } from "@/lib/settings";

/**
 * A child table, shown but not edited.
 *
 * The three grids on Livestock Settings — the feed source warehouses in search
 * order, the bought-in concentrates, the growth ladder — are ordered lists whose
 * rows link to other doctypes. A grid editor is its own piece of work, and a
 * half-built one that drops a row's position or writes an item that does not
 * exist would be worse than none: the feed warehouse order decides which store
 * a Work Order transfers from, and the ladder decides which herd a heifer
 * climbs into next.
 *
 * So the rows are shown in full, and the page says plainly where they are
 * edited. It does not present a disabled-looking form and hope nobody tries.
 */
export function ChildTableView({ table }: { table: SettingsTable }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-[13px] font-semibold text-[var(--sd-ink)]">{table.label}</h4>
        <span className="inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--sd-muted)]">
          <Lock className="h-3 w-3" />
          Read only here
        </span>
      </div>

      {table.description && (
        <p className="max-w-[64rem] text-[11px] leading-relaxed text-[var(--sd-quiet)]">
          {table.description}
        </p>
      )}

      <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10 text-right">#</TableHead>
              {table.columns.map((column) => (
                <TableHead key={column.fieldname}>{column.label}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {table.rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={table.columns.length + 1}
                  className="text-[13px] text-[var(--sd-quiet)]"
                >
                  No rows.
                </TableCell>
              </TableRow>
            )}
            {table.rows.map((row, i) => (
              <TableRow key={String(row.idx ?? i)}>
                <TableCell className="text-right tabular-nums text-[var(--sd-quiet)]">
                  {String(row.idx ?? i + 1)}
                </TableCell>
                {table.columns.map((column) => {
                  const cell = row[column.fieldname];
                  return (
                    <TableCell key={column.fieldname}>
                      {column.fieldtype === "Check"
                        ? Number(cell ?? 0)
                          ? "Yes"
                          : "No"
                        : cell === null || cell === undefined || cell === ""
                          ? "—"
                          : String(cell)}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <p className="text-[11px] text-[var(--sd-quiet)]">
        Rows are added, reordered and removed on the desk for now —{" "}
        <a
          href="/app/livestock-settings"
          className="font-medium text-[var(--sd-ink)] underline underline-offset-4"
        >
          Livestock Settings
        </a>
        . Order matters in this grid, so it is left where the grid editor is.
      </p>
    </div>
  );
}
