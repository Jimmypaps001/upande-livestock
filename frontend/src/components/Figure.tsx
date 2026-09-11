import * as React from "react";

import { cn } from "@/lib/utils";

/** What a Figure shows when the farm has not recorded anything yet. */
const EMPTY = "—";

/**
 * One number and what it means. The app's only way of showing a headline
 * figure, so the same quantity is the same size everywhere.
 *
 * A figure with nothing behind it is drawn quiet rather than bold: an em dash
 * set at 26px in full ink reads as a stray minus sign and draws the eye to the
 * one cell that has nothing to say.
 */
export function Figure({
  label,
  value,
  unit,
  hint,
}: {
  label: string;
  value: string;
  unit?: string;
  hint?: string;
}) {
  const empty = value === EMPTY || value === "";
  return (
    <div className="flex min-w-0 flex-col gap-1.5 bg-[var(--sd-card)] px-5 py-4">
      <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
        {label}
      </span>
      <span
        className={cn(
          "text-[26px] font-semibold leading-none tracking-[-0.025em] tabular-nums",
          empty ? "text-[var(--sd-quiet)]" : "text-[var(--sd-ink)]",
        )}
      >
        {empty ? EMPTY : value}
        {unit && !empty && (
          <span className="ml-1 text-[12px] font-medium text-[var(--sd-muted)]">
            {unit}
          </span>
        )}
      </span>
      <span className="min-h-[1rem] text-[11px] text-[var(--sd-quiet)]">
        {hint || ""}
      </span>
    </div>
  );
}

/**
 * The figures under a chart or a table — a ruled table of numbers, not a
 * coloured slab.
 *
 * It used to be a beige panel, which put a block of colour under every chart
 * and made the summary look heavier than the thing it summarised. The cells
 * are now the card's own white and the structure comes from the rules between
 * them: a 1px grid drawn by letting the container's border colour show through
 * a one-pixel gap. Rules separate without adding weight, which is the whole
 * difference between reading this as part of the card and reading it as
 * something dropped on top.
 *
 * THE COLUMN COUNT COMES FROM THE CHILDREN. A row of two in a four-column grid
 * leaves two cells holding nothing, and once the cells are white those empty
 * cells are two grey rectangles at the end of the row. The beige fill used to
 * hide that, which is exactly why it survived unnoticed until the fill went.
 * Asking the caller to pick a different component for two figures would leave
 * the same trap set for the next person.
 */
export function FigureRow({ children }: { children: React.ReactNode }) {
  const count = React.Children.toArray(children).length;
  const columns =
    count <= 1
      ? "grid-cols-1"
      : count === 2
        ? "grid-cols-2"
        : count === 3
          ? "grid-cols-2 sm:grid-cols-3"
          : "grid-cols-2 sm:grid-cols-4";

  return (
    <div
      className={cn(
        "grid gap-px overflow-hidden rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-line)]",
        columns,
      )}
    >
      {children}
    </div>
  );
}
