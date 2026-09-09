import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The server's own words, unedited.
 *
 * Every livestock endpoint answers `{"error": "..."}` rather than raising, and
 * those messages are written for a farm worker: a refused backdated feed run
 * names each short item, what the store held on that day, and the earliest date
 * the run would work. Rewording or truncating it would take away the only
 * instruction the operator has, so this renders the string as it arrived —
 * including its blank lines, which is what `whitespace-pre-line` is for.
 */
export function Notice({
  tone,
  children,
  className,
}: {
  tone: "error" | "ok" | "info";
  children: React.ReactNode;
  className?: string;
}) {
  const Icon = tone === "error" ? AlertTriangle : tone === "ok" ? CheckCircle2 : Info;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-[var(--sd-radius-lg)] border px-3.5 py-3 text-[13px] leading-relaxed whitespace-pre-line",
        tone === "error" &&
          "border-[rgba(196,48,43,0.24)] bg-[rgba(196,48,43,0.06)] text-[var(--sd-sev-critical)]",
        tone === "ok" &&
          "border-[rgba(63,143,79,0.28)] bg-[rgba(63,143,79,0.07)] text-[var(--sd-sev-moderate)]",
        tone === "info" && "border-[var(--sd-line)] bg-[var(--sd-bg-soft)] text-[var(--sd-muted)]",
        className,
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** An operator instruction that is not a failure — the accountability warnings
 *  on the backdate toggle and the manual tab. Amber, like the desk block. */
export function AmberNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded-[var(--sd-radius-lg)] border border-[var(--sd-amber-line)] bg-[var(--sd-amber-bg)] px-3.5 py-3 text-[13px] leading-relaxed text-[var(--sd-amber)]">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** The amber Backdated / Manual marks. A run that is not an ordinary one is
 *  labelled as such wherever it appears. */
export function Mark({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] border border-[var(--sd-amber-line)] bg-[var(--sd-amber-bg)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--sd-amber)]">
      {children}
    </span>
  );
}

export function Pill({
  tone,
  children,
}: {
  tone: "ok" | "short" | "mute";
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[var(--sd-radius-pill)] px-2.5 py-1 text-[11px] font-medium",
        tone === "ok" && "bg-[rgba(63,143,79,0.10)] text-[var(--sd-sev-moderate)]",
        tone === "short" && "bg-[rgba(196,48,43,0.09)] text-[var(--sd-sev-critical)]",
        tone === "mute" && "bg-[var(--sd-bg-soft)] text-[var(--sd-muted)]",
      )}
    >
      {children}
    </span>
  );
}
