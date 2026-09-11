/** One number and what it means. The app's only way of showing a headline
 *  figure, so the same quantity is the same size everywhere. */
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
  return (
    <div className="flex min-w-0 flex-col gap-1.5 bg-[var(--sd-bg-soft)] px-4 py-4">
      <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
        {label}
      </span>
      <span className="text-[26px] font-semibold leading-none tracking-[-0.025em] text-[var(--sd-ink)] tabular-nums">
        {value}
        {unit && (
          <span className="ml-1 text-[12px] font-medium text-[var(--sd-muted)]">{unit}</span>
        )}
      </span>
      {hint && <span className="text-[11px] text-[var(--sd-quiet)]">{hint}</span>}
    </div>
  );
}

/**
 * The strip those figures sit in — a recess in the card, not a slab on it.
 *
 * The fill is one step below the card rather than the four it used to be, and
 * the figures are separated by hairlines instead of by gap alone. Columns
 * divided by whitespace read as four unrelated numbers; divided by a rule they
 * read as one set, which is what they are.
 */
export function FigureRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-line-soft)] sm:grid-cols-4">
      {children}
    </div>
  );
}
