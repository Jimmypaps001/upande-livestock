import { PORTIONS } from "@/lib/feeding";
import { cn } from "@/lib/utils";

/**
 * How much of the day this run is: half, or all of it.
 *
 * The farm feeds twice a day, so those are the only two answers. The control
 * is a two-position slider rather than a number field on purpose — the
 * operator never types a decimal and never sees one. What they see is the
 * kilograms the choice puts in the trough, which the caller renders live
 * beside it.
 */
export function PortionSlider({
  portion,
  onChange,
  disabled,
}: {
  portion: number;
  onChange: (next: number) => void;
  disabled?: boolean;
}) {
  const index = Math.max(
    0,
    PORTIONS.findIndex((p) => p.portion === portion),
  );

  return (
    <div className="flex flex-col gap-2">
      <div className="relative flex h-10 items-center rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] p-1">
        {/* The travelling thumb — a pill that slides between the two stops. */}
        <div
          className="pointer-events-none absolute top-1 bottom-1 left-1 w-[calc(50%-0.25rem)] rounded-[var(--sd-radius-pill)] bg-[var(--sd-card)] shadow-[0_1px_0_rgba(10,10,10,0.06),0_6px_16px_-10px_rgba(10,10,10,0.35)] transition-transform duration-200 ease-out"
          style={{ transform: `translateX(${index * 100}%)` }}
          aria-hidden
        />
        {PORTIONS.map((p, i) => (
          <button
            key={p.portion}
            type="button"
            disabled={disabled}
            aria-pressed={i === index}
            onClick={() => onChange(p.portion)}
            className={cn(
              "relative z-10 flex-1 rounded-[var(--sd-radius-pill)] py-1.5 text-[13px] font-medium transition-colors disabled:opacity-50",
              i === index ? "text-[var(--sd-ink)]" : "text-[var(--sd-quiet)]",
            )}
          >
            {p.label}
          </button>
        ))}
      </div>
      {/* The real input, so the control is a slider to the keyboard and to
          assistive tech as well as to the mouse. Two stops, no decimals. */}
      <input
        type="range"
        min={0}
        max={PORTIONS.length - 1}
        step={1}
        value={index}
        disabled={disabled}
        aria-label="How much of the day this run is"
        aria-valuetext={PORTIONS[index].label}
        onChange={(e) => onChange(PORTIONS[Number(e.target.value)].portion)}
        className="h-1 w-full cursor-pointer appearance-none rounded-full bg-[var(--sd-line)] accent-[var(--sd-ink)] disabled:cursor-not-allowed"
      />
    </div>
  );
}
