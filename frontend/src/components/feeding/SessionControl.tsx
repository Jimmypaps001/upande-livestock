import { cn } from "@/lib/utils";
import { SESSION_LABEL, choiceLabel, type SessionChoice, type SessionState } from "@/lib/feed-sessions";

/**
 * Full day / Half day, chosen before Mix. Half is the next half: session 1 of
 * 2 on an unfed day, session 2 of 2 once the first half is fed.
 */
export function SessionControl({
  value,
  onChange,
  state,
  disabled,
  allowed,
}: {
  value: SessionChoice;
  onChange: (next: SessionChoice) => void;
  state?: SessionState | null;
  disabled?: boolean;
  /** The choices to offer; one the user may not make is left out, not greyed. */
  allowed?: SessionChoice[];
}) {
  const options: Array<{ key: SessionChoice; label: string }> = (
    [
      { key: "Full", label: SESSION_LABEL.Full },
      { key: "Half", label: choiceLabel("Half", state) },
    ] as Array<{ key: SessionChoice; label: string }>
  ).filter((o) => !allowed || allowed.includes(o.key));
  if (options.length === 0) return null;
  return (
    <div role="radiogroup" aria-label="Full day or half day" className="inline-flex flex-wrap gap-1 rounded-lg border border-[var(--sd-line)] p-0.5">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="radio"
          aria-checked={value === o.key}
          disabled={disabled}
          onClick={() => onChange(o.key)}
          className={cn(
            "rounded-md px-3 py-1.5 text-[13px] transition-colors",
            value === o.key
              ? "bg-[var(--sd-ink)] font-semibold text-white"
              : "text-[var(--sd-muted)] hover:bg-[var(--sd-line)]",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
