import { coverLabel, type CoverDetail, type CoverState } from "@/lib/animals";
import { cn } from "@/lib/utils";

const TONE: Record<string, string> = {
  insured: "var(--sd-data-green)",
  expiring: "var(--sd-data-amber)",
  expired: "var(--sd-data-red)",
  none: "var(--sd-quiet)",
};

/**
 * Whether she is under insurance cover, as Upande Asset knows it. Draws nothing
 * for an animal with no asset or a site with no insurance module, and in the
 * list nothing for "no cover" either: three hundred "No cover" pills would say
 * the same absence three hundred times. The profile (`detail`) does name it.
 */
export function CoverBadge({
  state,
  detail,
  info,
  className,
}: {
  state: CoverState | undefined;
  detail?: boolean;
  info?: CoverDetail | null;
  className?: string;
}) {
  const label = coverLabel(state, detail);
  if (!label || !state) return null;
  const tone = TONE[state];
  const title = info?.end
    ? `${info.insurer || "Insurer"}${info.policyNumber ? ` · ${info.policyNumber}` : ""} · until ${info.end}`
    : label;
  return (
    <span
      data-testid="cover-badge"
      data-cover={state}
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center rounded-[var(--sd-radius-pill)] px-2 py-0.5 text-[10.5px] font-semibold",
        className,
      )}
      style={{
        color: `color-mix(in srgb, ${tone} 80%, var(--sd-ink))`,
        background: `color-mix(in srgb, ${tone} 14%, transparent)`,
      }}
    >
      {label}
    </span>
  );
}
