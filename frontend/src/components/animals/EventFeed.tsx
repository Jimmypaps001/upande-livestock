import {
  Activity,
  ArrowRightLeft,
  Baby,
  CircleSlash,
  Droplet,
  HeartPulse,
  Scale,
  Sparkle,
  type LucideIcon,
} from "lucide-react";
import { MILESTONE_TONE, type Milestone, type MilestoneKind } from "@/lib/animals";

/**
 * Everything that has happened to her, newest first.
 *
 * The same events the timeline draws, read as a column. The timeline answers
 * "when, and how far apart"; this answers "what, exactly" — and it is the one
 * a person scrolls when they already know roughly when and want the detail.
 *
 * Grouped by year, because an animal with six lactations behind her has sixty
 * rows and an ungrouped sixty-row list is a wall.
 */

const ICON: Record<MilestoneKind, LucideIcon> = {
  birth: Sparkle,
  movement: ArrowRightLeft,
  service: Droplet,
  confirmed: HeartPulse,
  calving: Baby,
  abortion: CircleSlash,
  drying: Activity,
  health: HeartPulse,
  weight: Scale,
};

export function EventFeed({ milestones }: { milestones: Milestone[] }) {
  const byYear = new Map<string, Milestone[]>();
  for (const m of [...milestones].sort((a, b) => (a.on < b.on ? 1 : -1))) {
    const y = m.on.slice(0, 4);
    if (!byYear.has(y)) byYear.set(y, []);
    byYear.get(y)!.push(m);
  }

  if (!milestones.length) {
    return (
      <p className="text-[13px] text-[var(--sd-muted)]">
        Nothing recorded against her yet. Events booked anywhere in the app will
        appear here.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {[...byYear.entries()].map(([year, rows]) => (
        <section key={year} className="flex flex-col gap-1">
          <div className="flex items-center gap-3 pb-1">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--sd-quiet)]">
              {year}
            </h3>
            <span className="h-px flex-1 bg-[var(--sd-line-soft)]" />
            <span className="text-[11px] tabular-nums text-[var(--sd-quiet)]">
              {rows.length}
            </span>
          </div>

          <ol className="flex flex-col">
            {rows.map((m, i) => {
              const Icon = ICON[m.kind];
              return (
                <li
                  key={`${m.on}-${i}`}
                  className="group flex items-start gap-3 rounded-[var(--sd-radius)] px-2 py-2.5 transition-colors hover:bg-[var(--sd-bg-soft)]"
                >
                  <span
                    className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                    style={{ background: `color-mix(in srgb, ${MILESTONE_TONE[m.kind]} 14%, transparent)` }}
                  >
                    <Icon
                      className="h-3.5 w-3.5"
                      strokeWidth={1.75}
                      style={{ color: MILESTONE_TONE[m.kind] }}
                    />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-[13.5px] font-medium text-[var(--sd-ink)]">
                      {m.label}
                    </span>
                    {m.detail && (
                      <span className="text-[12px] text-[var(--sd-muted)]">{m.detail}</span>
                    )}
                  </span>
                  <span className="shrink-0 pt-0.5 text-[11.5px] tabular-nums text-[var(--sd-quiet)]">
                    {m.on.slice(5)}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}
