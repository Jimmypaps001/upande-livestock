import { CYCLE_ORDER, STAGES, type CycleState } from "@/lib/animals";
import { cn } from "@/lib/utils";

/**
 * Where she stands in the loop between one calving and the next.
 *
 * A dairy cow's year is a circle — calve, wait, serve, carry, dry off, calve
 * again — and every textbook on the subject draws it as one. Rendering it as a
 * row of status chips would throw away the one thing the shape is telling you:
 * that this is a cycle she has been round before and will go round again, and
 * that the gap between two points on it is time she is either paying for or
 * being paid for.
 *
 * The ring is proportioned by days, not by stage count. The carrying arc is
 * more than half the circle because gestation is 280 of roughly 400 days, and
 * a diagram that gave "served" and "in calf" equal quarters would quietly
 * misteach the thing it exists to explain.
 *
 * Drawn by hand in SVG, as the milk chart is: this app carries no charting
 * dependency and one ring does not earn a hundred kilobytes over a rural
 * connection.
 */

/** Typical length of each arc, in days, for an Ayrshire on a 400-day interval. */
const SPAN: Record<string, number> = {
  fresh: 21,
  open: 39,
  served: 35,
  confirmed: 245,
  dry: 60,
};

const SIZE = 260;
const C = SIZE / 2;
const R = 96;
const TRACK = 15;
const GAP_DEG = 2.6;

function polar(angleDeg: number, radius: number) {
  const a = ((angleDeg - 90) * Math.PI) / 180;
  return { x: C + radius * Math.cos(a), y: C + radius * Math.sin(a) };
}

function arcPath(fromDeg: number, toDeg: number, radius: number) {
  const s = polar(fromDeg, radius);
  const e = polar(toDeg, radius);
  const large = toDeg - fromDeg > 180 ? 1 : 0;
  return `M ${s.x} ${s.y} A ${radius} ${radius} 0 ${large} 1 ${e.x} ${e.y}`;
}

export function CycleRing({ cycle }: { cycle: CycleState }) {
  const total = CYCLE_ORDER.reduce((sum, s) => sum + SPAN[s], 0);

  // Lay the stages out round the circle, and work out where she is inside her
  // own arc — capped, because a cow who is late is still in that stage, and a
  // marker that ran past the end of the arc would say she had moved on.
  let cursor = 0;
  const arcs = CYCLE_ORDER.map((stage) => {
    const sweep = (SPAN[stage] / total) * 360;
    const arc = { stage, from: cursor, to: cursor + sweep, sweep };
    cursor += sweep;
    return arc;
  });

  const here = arcs.find((a) => a.stage === cycle.stage);
  const within = here ? Math.min(1, cycle.dayInStage / SPAN[here.stage]) : 0;
  const markerDeg = here ? here.from + here.sweep * within : null;
  const stage = STAGES[cycle.stage];
  const outside = cycle.stage === "heifer" || cycle.stage === "retired";

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:gap-7">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="h-[220px] w-[220px] shrink-0"
        role="img"
        aria-label={`Cycle position: ${stage.label}`}
      >
        {/* the track the arcs sit on, so an unreached stage still reads as part
            of the loop rather than as missing */}
        <circle cx={C} cy={C} r={R} fill="none" stroke="var(--sd-line-soft)" strokeWidth={TRACK} />

        {arcs.map((a) => {
          const isHere = !outside && a.stage === cycle.stage;
          return (
            <path
              key={a.stage}
              d={arcPath(a.from + GAP_DEG / 2, a.to - GAP_DEG / 2, R)}
              fill="none"
              stroke={STAGES[a.stage].tone}
              strokeWidth={TRACK}
              strokeLinecap="butt"
              opacity={outside ? 0.18 : isHere ? 1 : 0.26}
            />
          );
        })}

        {/* how far through the current arc she is */}
        {here && !outside && markerDeg !== null && (
          <>
            <path
              d={arcPath(here.from + GAP_DEG / 2, Math.max(here.from + GAP_DEG / 2 + 0.01, markerDeg), R)}
              fill="none"
              stroke={stage.tone}
              strokeWidth={TRACK}
              strokeLinecap="butt"
              opacity={0.55}
            />
            <circle
              cx={polar(markerDeg, R).x}
              cy={polar(markerDeg, R).y}
              r={9}
              fill="var(--sd-card)"
              stroke={stage.tone}
              strokeWidth={4}
            />
          </>
        )}

        <text
          x={C} y={C - 20}
          textAnchor="middle"
          className="fill-[var(--sd-quiet)] text-[9px] font-medium uppercase"
          style={{ letterSpacing: "0.18em" }}
        >
          {outside ? "Not in the loop" : "Day " + cycle.dayInStage}
        </text>
        <text
          x={C} y={C + 8}
          textAnchor="middle"
          className="fill-[var(--sd-ink)] text-[25px] font-semibold"
          style={{ letterSpacing: "-0.02em" }}
        >
          {stage.label}
        </text>
        <text x={C} y={C + 28} textAnchor="middle" className="fill-[var(--sd-muted)] text-[11px]">
          {stage.note}
        </text>
      </svg>

      <ol className="flex w-full min-w-0 flex-col gap-0.5">
        {CYCLE_ORDER.map((s) => {
          const isHere = !outside && s === cycle.stage;
          const passed = !outside && CYCLE_ORDER.indexOf(s) < CYCLE_ORDER.indexOf(cycle.stage);
          return (
            <li
              key={s}
              className={cn(
                "flex items-center gap-2.5 rounded-[var(--sd-radius)] px-2.5 py-1.5 transition-colors",
                isHere && "bg-[var(--sd-bg-soft)]",
              )}
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{
                  background: STAGES[s].tone,
                  opacity: isHere ? 1 : passed ? 0.5 : 0.22,
                }}
              />
              <span
                className={cn(
                  "truncate text-[13px]",
                  isHere ? "font-semibold text-[var(--sd-ink)]" : "text-[var(--sd-muted)]",
                )}
              >
                {STAGES[s].label}
              </span>
              <span className="ml-auto shrink-0 text-[11px] tabular-nums text-[var(--sd-quiet)]">
                {SPAN[s]}d
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}


export function CycleRingSkeleton() {
  // The ring is h-[220px] w-[220px] and the notes sit beside it; the box
  // below is that box, so the wheel lands where the placeholder was.
  return (
    <div className="flex flex-wrap items-center gap-6" aria-hidden>
      <div className="h-[220px] w-[220px] shrink-0 animate-pulse rounded bg-[var(--sd-bg-soft)] !rounded-full" />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-[13px] animate-pulse rounded bg-[var(--sd-bg-soft)]" style={{ width: `${60 + i * 8}%` }} />
        ))}
      </div>
    </div>
  );
}
