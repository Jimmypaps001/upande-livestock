import { cn } from "@/lib/utils";

/**
 * Placeholders shaped like the thing that is coming.
 *
 * A spinner says "wait"; a skeleton says "wait, and here is where it will be".
 * The second is worth building only if the box really is the same box — a
 * placeholder half the height of its content makes the page jump when the data
 * lands, which is worse than the spinner it replaced. So each of these takes
 * the dimension that the real component is built on: `MilkChart` is 320px tall
 * and `RunOutChart` 300, both by a constant at the top of their file, and the
 * caller passes the same number.
 */

export function ChartSkeleton({ height }: { height: number }) {
  return (
    <div
      className="w-full animate-pulse rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)]"
      style={{ height }}
      aria-hidden
    />
  );
}

/**
 * Rows of a list or a table, at the height the real rows sit at.
 *
 * The widths vary down the column on purpose. A block of identical bars reads
 * as a loading graphic; bars of different lengths read as text that has not
 * arrived, which is what it is.
 */
export function RowsSkeleton({
  rows = 5,
  className,
}: {
  rows?: number;
  className?: string;
}) {
  const widths = ["82%", "64%", "74%", "58%", "70%", "86%", "62%", "78%"];
  return (
    <div className={cn("flex flex-col gap-1", className)} aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-3 py-2.5">
          <div
            className="h-[13px] animate-pulse rounded bg-[var(--sd-bg-soft)]"
            style={{ width: widths[i % widths.length] }}
          />
        </div>
      ))}
    </div>
  );
}

/** A single bar at text height, for a line that has not arrived. */
export function TextSkeleton({ width = "12ch" }: { width?: string }) {
  return (
    <span
      className="inline-block h-[13px] animate-pulse rounded bg-[var(--sd-bg-soft)] align-middle"
      style={{ width }}
      aria-hidden
    />
  );
}
