import { useMemo, useState } from "react";
import {
  MILESTONE_TONE,
  type HerdSpell,
  type Milestone,
  type MilestoneKind,
} from "@/lib/animals";
import { cn } from "@/lib/utils";

/**
 * Her whole life on one line, to scale.
 *
 * Two things are drawn against the same axis because they answer each other:
 * the band underneath is which herd she was standing in, and the marks above
 * are what happened to her. Read together they say things neither says alone —
 * that she was served three weeks after arriving in the bulling herd, that the
 * abortion came in the middle of her longest spell in milk.
 *
 * The axis is real time, not one slot per event. A timeline with evenly spaced
 * milestones is a list wearing a line's clothing: it hides the eighteen quiet
 * months and the fortnight when everything happened at once, which is the
 * whole of what a farm wants to see.
 */

const KIND_LABEL: Record<MilestoneKind, string> = {
  birth: "Born",
  movement: "Moved",
  service: "Served",
  confirmed: "Confirmed",
  calving: "Calved",
  abortion: "Abortion",
  drying: "Dried off",
  health: "Health",
  weight: "Weighed",
};

/** A quiet, repeatable colour per herd, keyed off the name so a herd keeps its
 *  band colour from one animal's timeline to the next. */
const BAND_TONES = [
  "var(--sd-data-indigo)",
  "var(--sd-data-cyan)",
  "var(--sd-data-green)",
  "var(--sd-data-amber)",
  "var(--sd-data-purple)",
  "var(--sd-data-pink)",
];
function bandTone(herd: string): string {
  let h = 0;
  for (let i = 0; i < herd.length; i += 1) h = (h * 31 + herd.charCodeAt(i)) >>> 0;
  return BAND_TONES[h % BAND_TONES.length];
}

export function LifeTimeline({
  bornOn,
  milestones,
  spells,
}: {
  bornOn: string | null;
  milestones: Milestone[];
  spells: HerdSpell[];
}) {
  const [open, setOpen] = useState<number | null>(null);

  const model = useMemo(() => {
    const start = new Date(bornOn || milestones[0]?.on || Date.now()).getTime();
    const end = Date.now();
    const span = Math.max(1, end - start);
    const at = (iso: string) =>
      Math.min(100, Math.max(0, ((new Date(iso).getTime() - start) / span) * 100));

    // Years down the axis, so a reader can place an event without arithmetic.
    const ticks: { pct: number; label: string }[] = [];
    const firstYear = new Date(start).getFullYear();
    const lastYear = new Date(end).getFullYear();
    for (let y = firstYear; y <= lastYear; y += 1) {
      const t = new Date(`${y}-01-01`).getTime();
      if (t < start || t > end) continue;
      ticks.push({ pct: ((t - start) / span) * 100, label: String(y) });
    }

    return {
      ticks,
      bands: spells.map((s) => ({
        ...s,
        left: at(s.from),
        width: Math.max(0.8, at(s.to || new Date().toISOString()) - at(s.from)),
        tone: bandTone(s.herd),
      })),
      marks: milestones
        .map((m, i) => ({ ...m, i, pct: at(m.on) }))
        .sort((a, b) => a.pct - b.pct),
    };
  }, [bornOn, milestones, spells]);

  if (!model.marks.length) {
    return (
      <p className="text-[13px] text-[var(--sd-muted)]">
        Nothing recorded against her yet.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* the marks, stem-and-dot so a dense run stays readable */}
      <div className="relative h-[76px]">
        {model.marks.map((m) => {
          const isOpen = open === m.i;
          return (
            <button
              key={`${m.on}-${m.i}`}
              type="button"
              onClick={() => setOpen(isOpen ? null : m.i)}
              // inset-y-0, not bottom-0: the stem below the dot is `flex-1`,
              // which needs a parent with a real height to grow into. Left to
              // size itself the button was 10px tall, the stem collapsed to
              // nothing, and the dots floated unattached above the band.
              className="group absolute inset-y-0 flex w-3 -translate-x-1/2 flex-col items-center focus:outline-none"
              style={{ left: `${m.pct}%` }}
              aria-label={`${KIND_LABEL[m.kind]} — ${m.label}, ${m.on}`}
            >
              <span
                className={cn(
                  "h-3 w-3 shrink-0 rounded-full border-2 border-[var(--sd-card)] transition-transform",
                  isOpen ? "scale-125" : "group-hover:scale-125",
                )}
                style={{ background: MILESTONE_TONE[m.kind] }}
              />
              <span
                className="w-px flex-1 transition-colors"
                style={{ background: isOpen ? MILESTONE_TONE[m.kind] : "var(--sd-line)" }}
              />
            </button>
          );
        })}
      </div>

      {/* the herd she stood in, on the same axis */}
      <div className="relative flex h-7 w-full overflow-hidden rounded-[var(--sd-radius)] bg-[var(--sd-bg-soft)]">
        {model.bands.map((b, i) => (
          <span
            key={`${b.herd}-${i}`}
            className="absolute top-0 h-full"
            style={{
              left: `${b.left}%`,
              width: `${b.width}%`,
              background: b.tone,
              opacity: 0.34,
              borderRight: i < model.bands.length - 1 ? "1px solid var(--sd-card)" : undefined,
            }}
            title={`${b.herd} · ${b.from} → ${b.to || "now"}`}
          />
        ))}
      </div>

      {/* the years */}
      <div className="relative h-4">
        {model.ticks.map((t) => (
          <span
            key={t.label}
            className="absolute -translate-x-1/2 text-[10px] tabular-nums text-[var(--sd-quiet)]"
            style={{ left: `${t.pct}%` }}
          >
            {t.label}
          </span>
        ))}
        <span className="absolute right-0 text-[10px] font-medium text-[var(--sd-muted)]">
          today
        </span>
      </div>

      {/* what the selected mark was */}
      <div className="min-h-[52px] rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3">
        {open === null ? (
          <p className="text-[12.5px] text-[var(--sd-quiet)]">
            Pick a marker to read what happened. The band beneath is the herd she was
            standing in at the time.
          </p>
        ) : (
          (() => {
            const m = model.marks.find((x) => x.i === open);
            if (!m) return null;
            const herd = model.bands.find(
              (b) => m.pct >= b.left && m.pct <= b.left + b.width,
            );
            return (
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span
                  className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em]"
                  style={{ color: MILESTONE_TONE[m.kind] }}
                >
                  <span className="h-2 w-2 rounded-full" style={{ background: MILESTONE_TONE[m.kind] }} />
                  {KIND_LABEL[m.kind]}
                </span>
                <span className="text-[14px] font-medium text-[var(--sd-ink)]">{m.label}</span>
                <span className="text-[12px] tabular-nums text-[var(--sd-muted)]">{m.on}</span>
                {herd && (
                  <span className="text-[12px] text-[var(--sd-quiet)]">in {herd.herd}</span>
                )}
                {m.detail && (
                  <span className="basis-full text-[12.5px] text-[var(--sd-muted)]">{m.detail}</span>
                )}
              </div>
            );
          })()
        )}
      </div>
    </div>
  );
}
