import { Notice } from "@/components/feeding/Notice";
import type { FeedDayStatus } from "@/lib/feeding";
import { fmt } from "@/lib/utils";

function Figure({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
        {label}
      </span>
      <span className="text-[22px] font-semibold leading-none tracking-[-0.02em] text-[var(--sd-ink)] tabular-nums">
        {value}
        {unit && (
          <span className="ml-1 text-[12px] font-medium text-[var(--sd-muted)]">{unit}</span>
        )}
      </span>
    </div>
  );
}

/**
 * How much of today's ration has gone out.
 *
 * Read from what was issued, not from what was planned: a run entered by hand
 * counts, and so does a day that went differently. The farm feeds twice, so
 * "what does this herd need" is not the question at the trough — "what is owed
 * now" is.
 */
export function DayStatus({ day }: { day: FeedDayStatus | null }) {
  if (!day) return null;
  const pct = day.day_kg ? Math.round((day.issued_kg / day.day_kg) * 100) : 0;
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-5 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-bg-soft)] px-4 py-4 sm:grid-cols-4">
        <Figure label="Today needs" value={fmt(day.day_kg)} unit="kg" />
        <Figure label="Fed so far" value={fmt(day.issued_kg)} unit="kg" />
        <Figure label="Still owed" value={fmt(day.remaining_kg)} unit="kg" />
        <Figure
          label="Runs"
          value={String(day.runs_done)}
          unit={`of ${day.runs_per_day}`}
        />
      </div>
      {day.complete ? (
        <Notice tone="ok">The day is fed — {pct}% of the ration has gone out.</Notice>
      ) : (
        <Notice tone="info">
          A fresh day offers half. Change it if this run is the whole day; nothing here
          forces two equal halves.
        </Notice>
      )}
    </div>
  );
}
