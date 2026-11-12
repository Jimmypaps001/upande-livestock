import { History } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * "Backdated": a record entered after the day it describes.
 *
 * Shown wherever such a record is listed — a calving typed in three months
 * late, a service back-recorded for it, a stock draft dated last March — so
 * nobody reads it as something that happened the day it appears. Amber, the
 * colour the feed page already uses for a backdated run (Notice.Mark), so the
 * farm learns one meaning for it.
 */
export function BackdatedBadge({ className }: { className?: string }) {
  return (
    <span
      data-testid="backdated-badge"
      title="Entered after the day it describes"
      className={cn(
        "inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] border border-[var(--sd-amber-line)] bg-[var(--sd-amber-bg)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--sd-amber)]",
        className,
      )}
    >
      <History className="h-3 w-3" strokeWidth={2.25} aria-hidden />
      Backdated
    </span>
  );
}

/** The subtle tint a backdated row carries, beside its badge. */
export const BACKDATED_TINT = "bg-[var(--sd-amber-tint)]";

/** The tint class for a row, or "" when it is a same-day record. */
export function backdatedTint(backdated: unknown): string {
  return backdated ? BACKDATED_TINT : "";
}
