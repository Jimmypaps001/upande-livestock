import { CheckCircle2, CircleSlash, Clock, Flag } from "lucide-react";
import { cn } from "@/lib/utils";
import { toneFor, type ReviewStatus } from "@/lib/culling";

/**
 * What a case is waiting on, at a glance.
 *
 * Coloured by whether somebody has to act, not by how bad the news is. A death
 * is not an error and a sale is not a success — the only question the queue
 * answers is whether this one is anybody's turn.
 */
export function CaseBadge({ status, waitingOn }: { status: ReviewStatus; waitingOn?: string }) {
  const tone = toneFor(status);
  const Icon =
    tone === "ready" ? Flag : tone === "done" ? CheckCircle2 : tone === "stopped" ? CircleSlash : Clock;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium",
        tone === "wait" && "bg-[var(--sd-bg-soft)] text-[var(--sd-muted)]",
        tone === "ready" && "bg-[rgba(63,143,79,0.10)] text-[var(--sd-sev-moderate)]",
        tone === "done" && "bg-[var(--sd-bg-soft)] text-[var(--sd-quiet)]",
        tone === "stopped" && "bg-[rgba(196,48,43,0.08)] text-[var(--sd-sev-critical)]",
      )}
    >
      <Icon className="h-3 w-3" strokeWidth={2} />
      {waitingOn ? `With ${waitingOn}` : status}
    </span>
  );
}
