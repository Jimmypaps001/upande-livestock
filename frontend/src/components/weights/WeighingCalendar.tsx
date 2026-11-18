import { useMemo, useState } from "react";
import type { DayButtonProps } from "react-day-picker";
import { Calendar } from "@/components/ui/calendar";
import type { GallagherPreview } from "@/lib/gallagher";
import { cn, parseYmd, ymd } from "@/lib/utils";

type PerDate = GallagherPreview["dates"]["per_date"][number];

const DOT =
  "after:pointer-events-none after:absolute after:bottom-0 after:left-1/2 after:size-1.5 after:-translate-x-1/2 after:rounded-full";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "14–16 Sep 2026", "30 Sep – 2 Oct 2026" or "14 Sep 2026". */
export function rangeLabel(from: string, to: string): string {
  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  const f = `${fd} ${MONTHS[fm - 1]}`;
  const t = `${td} ${MONTHS[tm - 1]}`;
  if (from === to) return `${f} ${fy}`;
  if (fy === ty && fm === tm) return `${fd}–${td} ${MONTHS[fm - 1]} ${fy}`;
  if (fy === ty) return `${f} – ${t} ${ty}`;
  return `${f} ${fy} – ${t} ${ty}`;
}

/** The one-line summary above the calendar. */
export function weighingSummary(p: GallagherPreview): string {
  const d = p.dates;
  if (!d.from || !d.to) return "No readable dates.";
  const n = d.per_date.length;
  const rows = d.per_date.reduce((a, x) => a + x.rows, 0);
  return `Weighed on ${n} day${n === 1 ? "" : "s"}, ${rangeLabel(d.from, d.to)} (${rows} row${rows === 1 ? "" : "s"})`;
}

/**
 * The file's weighing days on a small calendar: a day with weighings is
 * tinted and carries its row count, a red dot marks a day with future-dated
 * rows and an amber one a day with weights already recorded. Clicking a day
 * picks it; clicking it again clears it.
 */
export function WeighingCalendar({
  p,
  picked,
  onPick,
}: {
  p: GallagherPreview;
  picked: string | null;
  onPick: (day: string | null) => void;
}) {
  const days = p.dates.per_date;
  const by = useMemo(() => new Map(days.map((x) => [x.date, x])), [days]);
  const first = parseYmd(p.dates.from ?? "");
  const last = parseYmd(p.dates.to ?? "");
  const span = first && last ? (last.getFullYear() - first.getFullYear()) * 12 + last.getMonth() - first.getMonth() + 1 : 1;
  const [month, setMonth] = useState<Date | undefined>(first && new Date(first.getFullYear(), first.getMonth(), 1));
  if (!first || !last || days.length === 0) return null;

  const dates = (test: (x: PerDate) => boolean) => days.filter(test).map((x) => parseYmd(x.date)!);
  const DayButton = ({ day, modifiers, className, children, ...rest }: DayButtonProps) => {
    const x = !modifiers.outside ? by.get(ymd(day.date)) : undefined;
    const issues = [
      x?.future ? `${x.future} dated in the future` : "",
      x?.already_recorded ? `${x.already_recorded} already recorded` : "",
    ].filter(Boolean);
    return (
      <button
        {...rest}
        className={className}
        title={x ? [`${x.rows} row${x.rows === 1 ? "" : "s"}`, ...issues].join(", ") : undefined}
      >
        {children}
        {x && (
          <span className="pointer-events-none absolute -right-1 -top-1 min-w-3.5 rounded-full bg-[var(--sd-card)] px-0.5 text-[9px] font-medium leading-[14px] tabular-nums text-[var(--sd-muted)] shadow-[0_0_0_1px_var(--sd-line)]">
            {x.rows}
          </span>
        )}
      </button>
    );
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex w-fit max-w-full flex-col items-center rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] pb-1">
        <Calendar
          mode="single"
          month={month}
          onMonthChange={setMonth}
          numberOfMonths={Math.min(span, 3)}
          selected={picked ? parseYmd(picked) : undefined}
          onSelect={(_d, clicked) => onPick(picked === ymd(clicked) ? null : ymd(clicked))}
          required={false}
          showOutsideDays={false}
          className="p-2"
          modifiers={{
            weighed: dates(() => true),
            future: dates((x) => x.future > 0),
            already: dates((x) => x.already_recorded > 0),
          }}
          modifiersClassNames={{
            weighed: "[&>button]:bg-[var(--sd-card)] [&>button]:font-medium",
            future: cn(DOT, "after:bg-[var(--sd-data-red)]"),
            already: cn(DOT, "after:bg-[var(--sd-data-amber)]"),
          }}
          classNames={{
            selected:
              "rounded-full [&>button]:bg-[var(--sd-ink)] [&>button]:font-medium [&>button]:text-white [&>button]:hover:bg-[var(--sd-ink)] [&>button]:hover:text-white",
            months: "relative flex flex-col gap-2 sm:flex-row sm:gap-4",
            month: "w-full space-y-2",
          }}
          components={{ DayButton }}
        />
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 px-3 pb-1.5 text-[11.5px] text-[var(--sd-muted)]">
          <span>Number: rows that day</span>
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-[var(--sd-data-red)]" /> future date
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-[var(--sd-data-amber)]" /> already recorded
          </span>
        </div>
      </div>
    </div>
  );
}
