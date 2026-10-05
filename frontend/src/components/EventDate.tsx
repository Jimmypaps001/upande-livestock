import { useEffect } from "react";
import { Lock } from "lucide-react";
import { DatePicker } from "@/components/DatePicker";
import { usePostingDay } from "@/lib/posting-day";
import { parseYmd } from "@/lib/utils";

/**
 * The date a record is recorded against.
 *
 * While backdating is closed in Livestock Settings the date is today — the
 * server's today — and cannot be changed: it is shown read-only and the field's
 * value is "" so the form sends no date and the server dates the record itself.
 * That is what stops a browser in another time zone from turning an untouched
 * date into a refused backdated one. Open, it is a normal date picker up to
 * the server's today.
 */
export function EventDate({
  id,
  value,
  onChange,
}: {
  id?: string;
  value: string;
  onChange: (next: string) => void;
}) {
  const day = usePostingDay();
  const closed = day !== null && !day.backdating_open;

  useEffect(() => {
    // Closed: the record takes the server's today, so send nothing.
    if (closed && value !== "") onChange("");
    // Open: a blank field starts at the server's today.
    if (day?.backdating_open && value === "") onChange(day.today);
  }, [closed, day, value, onChange]);

  if (!day) {
    return <DatePicker id={id} value={value} onChange={onChange} disabled />;
  }
  if (closed) {
    const shown = parseYmd(day.today);
    return (
      <div className="flex flex-col gap-1">
        <div
          id={id}
          className="flex h-9 items-center gap-2 rounded-md border border-[var(--sd-line)] bg-[var(--sd-bg-soft)] px-3 text-[13px] text-[var(--sd-ink)]"
          aria-readonly="true"
        >
          <Lock className="h-3.5 w-3.5 text-[var(--sd-quiet)]" />
          {shown ? shown.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : day.today}
          <span className="text-[var(--sd-quiet)]">· today</span>
        </div>
        <span className="text-[11px] text-[var(--sd-quiet)]">
          Backdating is closed, so this is recorded against today.
        </span>
      </div>
    );
  }
  return <DatePicker id={id} value={value || day.today} max={day.today} onChange={onChange} />;
}
