import { cn } from "@/lib/utils";
import {
  sessionChipText,
  sessionFigures,
  stateLabel,
  type FeedSession,
  type SessionState,
} from "@/lib/feed-sessions";

/** Not fed / Half fed (1 of 2) / Fully fed. */
export function StateChip({ session }: { session?: SessionState | null }) {
  const state = session?.state ?? "not_fed";
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[11px] font-medium",
        state === "half_fed" && "bg-amber-100 text-amber-800",
        state === "fully_fed" && "bg-emerald-100 text-emerald-800",
        state === "not_fed" && "bg-[var(--sd-line)]",
      )}
    >
      {stateLabel(session)}
    </span>
  );
}

/** One chip per session: what was fed, amended or not, planned against fed. */
export function SessionChips({ sessions }: { sessions?: FeedSession[] | null }) {
  if (!sessions?.length) return null;
  return (
    <ul className="flex flex-col gap-1.5">
      {sessions.map((s, i) => (
        <li
          key={s.name ?? i}
          className="rounded-md border border-[var(--sd-line)] px-2.5 py-1.5 text-[12px]"
        >
          <span className="font-medium">{sessionChipText(s)}</span>
          <span className="ml-2 text-[var(--sd-quiet)]">{sessionFigures(s)}</span>
          {!!s.overridden && <span className="ml-2 text-amber-700">manager override</span>}
        </li>
      ))}
    </ul>
  );
}
