import { DOCK_LINE } from "@/lib/use-dock-progress";
import { cn } from "@/lib/utils";

/**
 * The rounded surface the title lands on.
 *
 * It holds a SLOT, not the title: an invisible copy of the text that reserves
 * exactly the width and height the real one will occupy, so the pill is
 * already the right size before the title arrives and does not grow around it
 * on landing. The real text flies in from the heading — see MorphingTitle.
 *
 * The pill itself fades and lifts a little so the surface arrives with the
 * text rather than waiting under it, but the title is never drawn twice.
 */
export function PageDock({
  eyebrow,
  title,
  docked,
  titleSlot,
  children,
}: {
  eyebrow: string;
  title: string;
  docked: boolean;
  /** Where the flying title comes to rest. */
  titleSlot: React.Ref<HTMLSpanElement>;
  children?: React.ReactNode;
}) {
  return (
    <div
      aria-hidden={!docked}
      className="pointer-events-none fixed inset-x-0 z-40 flex justify-center px-4"
      style={{ top: DOCK_LINE - 34 }}
    >
      <div
        className={cn(
          "flex max-w-full items-center gap-3 rounded-[var(--sd-radius-pill)]",
          "border border-[var(--sd-line-soft)] bg-[color-mix(in_srgb,var(--sd-card)_78%,transparent)]",
          "px-4 py-2 shadow-[var(--sd-shadow-3)] backdrop-blur-xl",
          "transition-[opacity,transform] duration-300 ease-out",
          docked
            ? "pointer-events-auto translate-y-0 opacity-100"
            : "pointer-events-none -translate-y-2 opacity-0",
        )}
      >
        <span className="h-px w-3.5 shrink-0 bg-[var(--sd-text)]" aria-hidden />
        <span className="flex min-w-0 items-baseline gap-2">
          {/* The landing slot. Invisible, but it holds the space — opacity
              rather than visibility so the heading it mirrors stays readable
              to a screen reader. */}
          <span
            ref={titleSlot}
            className="truncate text-[14px] font-semibold leading-[1.05] tracking-[-0.03em] opacity-0"
          >
            {title}
          </span>
          <span className="hidden truncate text-[11px] uppercase tracking-[0.14em] text-[var(--sd-quiet)] sm:inline">
            {eyebrow}
          </span>
        </span>
        {children && <span className="flex shrink-0 items-center gap-2">{children}</span>}
      </div>
    </div>
  );
}
