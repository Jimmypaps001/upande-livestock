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
    <div className="flex min-w-0 flex-col gap-1.5 px-5 py-4">
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
 * The figures under a chart or a table.
 *
 * One panel in a single lighter tone, with a soft shadow instead of an outline
 * — no rules between the columns and no border around them. The shadow is the
 * inset level, not a card's: this is a recess in the card, and giving it the
 * card's own shadow made it look like a slab floating on top of one. The fill is a
 * lighter warm paper than the card it sits on, which is all the separation a
 * summary strip needs; ruling it into cells made four related numbers look
 * like four unrelated ones, and a hard outline drew a box around something
 * that is part of the card rather than a thing sitting on it.
 *
 * THE COLUMN COUNT COMES FROM THE CHILDREN. A row of two figures in a
 * four-column grid leaves half the panel empty, which on the dashboard's
 * protein/SCC row meant a wide blank to the right of the last number. Asking
 * callers to reach for a different component for two figures would leave the
 * same trap set for whoever adds a third.
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
        "grid gap-y-4 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-1 py-1 shadow-[var(--sd-shadow-inset)]",
        columns,
      )}
    >
      {children}
    </div>
  );
}
