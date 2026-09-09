import { PORTIONS } from "@/lib/feeding";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

/**
 * How much of the day this run is: half, or all of it.
 *
 * The farm feeds twice a day, so those are the only two answers — off is
 * "Half day" (0.5), on is "Full day" (1.0), the fuller state. A bare switch
 * doesn't say which side is which, and reading it backwards means feeding a
 * herd twice what was intended, so both states are labelled either side of
 * the track, with the active one emphasised. The number itself never
 * renders here — the caller shows the live kilograms instead.
 */
export function PortionSwitch({
  portion,
  onChange,
  disabled,
}: {
  portion: number;
  onChange: (next: number) => void;
  disabled?: boolean;
}) {
  const full = portion === 1;
  const [half, whole] = PORTIONS;

  return (
    <div className="flex items-center gap-2.5">
      <span
        className={cn(
          "text-[13px] transition-colors",
          full ? "text-[var(--sd-quiet)]" : "font-semibold text-[var(--sd-ink)]",
        )}
      >
        {half.label}
      </span>
      <Switch
        checked={full}
        onCheckedChange={(checked) => onChange(checked ? whole.portion : half.portion)}
        disabled={disabled}
        aria-label="Portion for this run: half day or full day"
      />
      <span
        className={cn(
          "text-[13px] transition-colors",
          full ? "font-semibold text-[var(--sd-ink)]" : "text-[var(--sd-quiet)]",
        )}
      >
        {whole.label}
      </span>
    </div>
  );
}
