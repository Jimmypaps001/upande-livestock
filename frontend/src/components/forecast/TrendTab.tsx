import { ChartSkeleton } from "@/components/Loading";
import type { TrendPoint, TrendSeries, TrendView } from "@/lib/forecast";

const W = 640;
const H = 160;
const PAD = 8;
const SHADES = ["var(--sd-series-1)", "var(--sd-series-3)", "var(--sd-data-cyan)", "var(--sd-data-purple)", "var(--sd-data-green)"];

/** Weekly gain per herd as lines, with the herd's target as a dashed gold line. */
function SeriesChart({
  title,
  points,
  target,
  colour,
}: {
  title: string;
  points: TrendPoint[];
  target: number | null;
  colour: string;
}) {
  const vals = points.map((p) => p.avg_adg).filter((v): v is number => v !== null);
  const top = Math.max(0.1, ...vals, target ?? 0) * 1.15;
  const x = (i: number) => PAD + (points.length > 1 ? (i / (points.length - 1)) * (W - 2 * PAD) : (W - 2 * PAD) / 2);
  const y = (v: number) => H - PAD - (v / top) * (H - 2 * PAD);
  // A null week breaks the line instead of drawing a zero.
  let d = "";
  let pen = false;
  points.forEach((p, i) => {
    if (p.avg_adg === null) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(p.avg_adg).toFixed(1)} `;
    pen = true;
  });
  return (
    <div className="rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] p-3" data-testid="trend-series">
      <div className="mb-1 flex items-baseline justify-between text-[12.5px]">
        <span className="font-medium text-[var(--sd-ink)]">{title}</span>
        <span className="tabular-nums text-[var(--sd-muted)]">
          {target !== null ? `Target ${target.toFixed(2)} kg/day` : "No target set"}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-40 w-full" role="img" aria-label={`${title} weekly gain`}>
        {target !== null && (
          <line
            data-testid="target-line"
            x1={PAD}
            x2={W - PAD}
            y1={y(target)}
            y2={y(target)}
            stroke="var(--sd-target)"
            strokeWidth={1.5}
            strokeDasharray="5 4"
          />
        )}
        <path d={d} fill="none" stroke={colour} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) =>
          p.avg_adg === null ? null : <circle key={p.week_start} cx={x(i)} cy={y(p.avg_adg)} r={2.5} fill={colour} />,
        )}
      </svg>
    </div>
  );
}

export function TrendTab({ data, loading }: { data: TrendView | null; loading: boolean }) {
  if (!data) {
    return loading ? (
      <ChartSkeleton height={200} />
    ) : (
      <p className="px-1 py-6 text-center text-[13px] text-[var(--sd-muted)]">The trend could not be loaded.</p>
    );
  }
  const series: TrendSeries[] = data.series;
  return (
    <div className="flex flex-col gap-3">
      <SeriesChart title="Whole farm" points={data.farm} target={null} colour="var(--sd-ink)" />
      {series.map((s, i) => (
        <SeriesChart
          key={s.herd}
          title={s.herd}
          points={s.points}
          target={s.target_adg_kg}
          colour={SHADES[i % SHADES.length]}
        />
      ))}
    </div>
  );
}
