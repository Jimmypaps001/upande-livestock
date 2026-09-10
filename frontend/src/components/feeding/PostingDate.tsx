import { AmberNotice } from "@/components/feeding/Notice";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn, todayISO } from "@/lib/utils";

export const BACKDATE_WARNING =
  "This is a backdating page. You are not affecting stocks — apply wisely. " +
  "The system will run through afterwards.";

/**
 * Which day this page posts against — decided once, at the top, before the
 * operator touches a form.
 *
 * Off is Live: every run posts against today and the date field is inert, so
 * an ordinary entry cannot wander onto a past day by brushing a control. On is
 * Backdate: the field opens and the amber warning appears. Turning it back off
 * snaps the date to today, so the two states can never disagree.
 *
 * Two labels either side of the track, the way PortionSwitch does it: a bare
 * switch does not say which side is which, and reading this one backwards
 * means posting a real stock movement on the wrong day.
 *
 * `max` is today. A picker with no ceiling offers tomorrow, and a future run
 * is not treated as backdated by the server's own resolver — it would sail
 * through unstamped. The server refuses one too; this is the browser's half of
 * the same rule.
 */
export function PostingDate({
  backdating,
  onBackdatingChange,
  date,
  onDateChange,
  idPrefix = "posting",
}: {
  backdating: boolean;
  onBackdatingChange: (next: boolean) => void;
  date: string;
  onDateChange: (next: string) => void;
  idPrefix?: string;
}) {
  const today = todayISO();

  return (
    <div className="flex flex-col gap-3">
      <div
        className={cn(
          "flex flex-wrap items-center gap-x-6 gap-y-3 rounded-[var(--sd-radius-lg)] border px-4 py-3 transition-colors",
          backdating
            ? "border-[var(--sd-amber-line)] bg-[var(--sd-amber-bg)]"
            : "border-[var(--sd-line)] bg-[var(--sd-bg-soft)]",
        )}
      >
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              "text-[13px] transition-colors",
              backdating
                ? "text-[var(--sd-quiet)]"
                : "font-semibold text-[var(--sd-ink)]",
            )}
          >
            Live
          </span>
          <Switch
            checked={backdating}
            onCheckedChange={(checked) => {
              onBackdatingChange(checked);
              if (!checked) onDateChange(today);
            }}
            aria-label="Posting date: live (today) or backdated"
          />
          <span
            className={cn(
              "text-[13px] transition-colors",
              backdating
                ? "font-semibold text-[var(--sd-amber)]"
                : "text-[var(--sd-quiet)]",
            )}
          >
            Backdate
          </span>
        </div>

        <div className="flex items-center gap-2.5">
          <Label
            htmlFor={`${idPrefix}-date`}
            className={cn(
              "text-[var(--sd-muted)]",
              !backdating && "text-[var(--sd-quiet)]",
            )}
          >
            Date fed
          </Label>
          <Input
            id={`${idPrefix}-date`}
            type="date"
            className="w-[11rem]"
            value={backdating ? date : today}
            max={today}
            disabled={!backdating}
            onChange={(e) => onDateChange(e.target.value)}
          />
        </div>

        <span className="text-[12px] text-[var(--sd-quiet)]">
          {backdating
            ? "Every run on this page posts on the date above."
            : "Every run on this page posts today."}
        </span>
      </div>
      {backdating && <AmberNotice>{BACKDATE_WARNING}</AmberNotice>}
    </div>
  );
}
