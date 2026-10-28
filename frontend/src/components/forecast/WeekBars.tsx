import type { ForecastWeek } from "@/lib/forecast";

/** Head ready per week as plain bars; the figures sit in the table beneath. */
export function WeekBars({ weeks }: { weeks: ForecastWeek[] }) {
  const max = Math.max(1, ...weeks.map((w) => w.head));
  return (
    <div
      className="flex h-28 items-end gap-1.5 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] px-3 pb-2 pt-3"
      role="img"
      aria-label="Head ready per week"
    >
      {weeks.map((w) => (
        <div key={w.week_start} className="flex h-full min-w-0 flex-1 flex-col justify-end" title={`${w.week_start}: ${w.head} head`}>
          <div
            className="w-full rounded-t bg-[var(--sd-ink)]"
            style={{ height: `${(w.head / max) * 100}%`, minHeight: w.head ? 2 : 0 }}
          />
        </div>
      ))}
    </div>
  );
}
