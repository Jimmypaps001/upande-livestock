/**
 * Shared styling for the controls that sit in a card's head.
 *
 * `HEADER_PILL` is the trigger for a filter dropdown up there: a rounded chip
 * carrying its current value, with no label stacked above it. The label is the
 * value — "Every herd", "Last 30 days" — so a separate caption would say the
 * same thing twice and cost the vertical space that keeps the controls on the
 * title's line. The name reaches a screen reader through aria-label instead.
 *
 * Ported from the scouting frontend so both farm apps put their filters in the
 * same place and shape.
 */
export const HEADER_PILL =
  "h-9 w-auto min-w-[8rem] gap-2 rounded-full border-transparent bg-[var(--sd-card)] px-4 text-xs font-medium text-[var(--sd-ink)] shadow-[var(--sd-shadow-1)] transition-shadow hover:shadow-[var(--sd-shadow-2)] focus:ring-0";
