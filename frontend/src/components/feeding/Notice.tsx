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
 *
 * SOME OF THOSE MESSAGES CARRY MARKUP. Frappe's own `frappe.throw` takes HTML,
 * and the app uses it: refusing a calving with no confirmed pregnancy answers
 * with <b> headings and <br> line breaks laying out three numbered steps. Left
 * alone, a herdsman reads "<b>No active pregnancy to calve from</b><br><br>" —
 * the instruction is there and unreadable. So the tags are turned back into the
 * line breaks they meant and then dropped.
 *
 * The icon those headings used to carry was an emoji and is now a real one, so
 * a message can also arrive with an <img> in front of it. It goes the same way
 * as the <b>: stripped, because this is text.
 *
 * TURNED INTO TEXT, NOT RENDERED AS HTML. These strings pass through a server
 * but some of them carry things a person typed — an animal name, a note on a
 * case — and `dangerouslySetInnerHTML` on that is an injection waiting for the
 * one farm whose cow is called something unfortunate.
 */

const BLOCK_BREAK = /<\/?(br|p|div|li|h[1-6])[^>]*>/gi;
const ANY_TAG = /<[^>]+>/g;

export function plainText(value: React.ReactNode): React.ReactNode {
  if (typeof value !== "string") return value;
  if (!value.includes("<")) return value;
  return value
    .replace(BLOCK_BREAK, "\n")
    .replace(ANY_TAG, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
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
      <div className="min-w-0 flex-1">{plainText(children)}</div>
    </div>
  );
}

/** An operator instruction that is not a failure — the accountability warnings
 *  on the backdate toggle and the manual tab. Amber, like the desk block. */
export function AmberNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded-[var(--sd-radius-lg)] border border-[var(--sd-amber-line)] bg-[var(--sd-amber-bg)] px-3.5 py-3 text-[13px] leading-relaxed text-[var(--sd-amber)]">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">{plainText(children)}</div>
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
