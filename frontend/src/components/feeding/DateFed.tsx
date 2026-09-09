import { useState } from "react";
import { CalendarClock, X } from "lucide-react";
import { AmberNotice } from "@/components/feeding/Notice";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { todayISO } from "@/lib/utils";
import { cn } from "@/lib/utils";

export const BACKDATE_WARNING =
  "This is a backdating page. You are not affecting stocks — apply wisely. " +
  "The system will run through afterwards.";

/**
 * The date this run is posted on.
 *
 * Off by default: the field is hidden and pinned to today, so an ordinary
 * entry cannot wander onto a past day by touching the wrong control. The amber
 * toggle is the only way in, and turning it off snaps the date back to today.
 *
 * `max` is today. A picker with no ceiling offers tomorrow, and a future feed
 * run is not treated as backdated by the server's own resolver — it would sail
 * through unstamped and post real Stock Entries on a day that has not
 * happened. The server refuses one too; this is the browser's half of the
 * same rule.
 */
export function DateFed({
  value,
  onChange,
  idPrefix,
}: {
  value: string;
  onChange: (next: string) => void;
  idPrefix: string;
}) {
  const [on, setOn] = useState(false);
  const today = todayISO();

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-end gap-3">
        <button
          type="button"
          onClick={() => {
            const next = !on;
            setOn(next);
            if (!next) onChange(today);
          }}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-[var(--sd-radius-lg)] border px-3 text-[13px] font-medium transition-colors",
            on
              ? "border-[var(--sd-amber-line)] bg-[var(--sd-amber)] text-white"
              : "border-[var(--sd-amber-line)] bg-[var(--sd-amber-bg)] text-[var(--sd-amber)]",
          )}
        >
          {on ? <X className="h-3.5 w-3.5" /> : <CalendarClock className="h-3.5 w-3.5" />}
          {on ? "Backdating" : "Backdate"}
        </button>
        {on && (
          <div className="flex min-w-[10rem] flex-col gap-1.5">
            <Label htmlFor={`${idPrefix}-date`} className="text-[var(--sd-muted)]">
              Date fed
            </Label>
            <Input
              id={`${idPrefix}-date`}
              type="date"
              value={value}
              max={today}
              onChange={(e) => onChange(e.target.value)}
            />
          </div>
        )}
      </div>
      {on && <AmberNotice>{BACKDATE_WARNING}</AmberNotice>}
    </div>
  );
}
