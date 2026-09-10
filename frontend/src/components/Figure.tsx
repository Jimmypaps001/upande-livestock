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
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
        {label}
      </span>
      <span className="text-[22px] font-semibold leading-none tracking-[-0.02em] text-[var(--sd-ink)] tabular-nums">
        {value}
        {unit && (
          <span className="ml-1 text-[12px] font-medium text-[var(--sd-muted)]">{unit}</span>
        )}
      </span>
      {hint && <span className="text-[11px] text-[var(--sd-quiet)]">{hint}</span>}
    </div>
  );
}

/** The bordered strip those figures sit in. */
export function FigureRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-5 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-bg-soft)] px-4 py-4 sm:grid-cols-4">
      {children}
    </div>
  );
}
