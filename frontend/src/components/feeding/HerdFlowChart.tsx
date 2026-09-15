import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Where the animals will be, drawn by hand in SVG.
 *
 * This replaced a list. Twenty-three days of changes, twenty-eight of them on
 * one morning, came out as "1 from 0-2 to 2-4" twenty-eight times — every fact
 * present and none of them readable. The same data as lines says the thing in
 * one look: the calf pen empties, the bulling heifers fill, and the two happen
 * at different speeds.
 *
 * HEAD COUNT, NOT SHARE. Unlike the feed chart beside it — where silage at
 * 3,800 kg a day would flatten mineral at 30 — herds are all counted in the
 * same unit and are the same order of magnitude, so one scale is honest and
 * comparing them is the point.
 *
 * Only herds that MOVE are drawn. A bull pen that sits at twelve for sixty days
 * is a flat line saying nothing, and eleven flat lines would bury the four that
 * are doing something.
 */

export const HERD_FLOW_HEIGHT = 260;
const PAD = { top: 14, right: 150, bottom: 40, left: 44 };

/**
 * Herds, drawn down a greyscale ramp rather than across a set of hues.
 *
 * Every line here is the same quantity — head count — so a colour difference
 * was carrying nothing except "this is a different line", and six saturated
 * hues made the brightest one look like the important one. The ramp says the
 * same thing (these are different) and adds an order while it is at it: the
 * herd that moves most is the darkest.
 */
const TONES = [
  "var(--sd-series-1)",
  "var(--sd-series-2)",
  "var(--sd-series-3)",
  "var(--sd-series-4)",
  "var(--sd-series-5)",
  "var(--sd-series-6)",
];

function shortDate(iso: string): string {
  const [, m, d] = iso.split("-");
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(d)} ${months[Number(m) - 1] || ""}`.trim();
}

function useWidth() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(820);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const set = () => setWidth(Math.max(360, el.clientWidth));
    set();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", set);
      return () => window.removeEventListener("resize", set);
    }
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

export function HerdFlowChart({
  herds,
  dates,
  className,
}: {
  herds: Record<string, number[]>;
  dates: string[];
  className?: string;
}) {
  const [ref, width] = useWidth();

  const moving = Object.entries(herds)
    .filter(([, series]) => series.length > 1 && Math.min(...series) !== Math.max(...series))
    .sort((a, b) => Math.max(...b[1]) - Math.max(...a[1]))
    .slice(0, TONES.length);

  const plotW = Math.max(1, width - PAD.left - PAD.right);
  const plotH = HERD_FLOW_HEIGHT - PAD.top - PAD.bottom;
  const n = dates.length;
  const top = Math.max(1, ...moving.flatMap(([, s]) => s)) * 1.08;

  const x = (i: number) => PAD.left + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH;

  if (!moving.length) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-[var(--sd-radius-lg)] border border-dashed border-[var(--sd-line)] text-[13px] text-[var(--sd-quiet)]">
        No herd changes size in this window.
      </div>
    );
  }

  return (
    <div ref={ref} className={cn("w-full overflow-x-auto", className)}>
      <svg
        width={width}
        height={HERD_FLOW_HEIGHT}
        viewBox={`0 0 ${width} ${HERD_FLOW_HEIGHT}`}
        role="img"
        aria-label={`Head count per herd over ${n - 1} days. ${moving
          .map(([herd, s]) => `${herd}: ${s[0]} today, ${s[s.length - 1]} at the end`)
          .join("; ")}.`}
        className="block"
      >
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={PAD.left} x2={PAD.left + plotW} y1={y(top * f)} y2={y(top * f)}
                  stroke="var(--sd-line)" strokeWidth={1} />
            <text x={PAD.left - 8} y={y(top * f) + 4} textAnchor="end"
                  className="fill-[var(--sd-quiet)] text-[11px] tabular-nums">
              {Math.round(top * f)}
            </text>
          </g>
        ))}

        {moving.map(([herd, series], i) => {
          const tone = TONES[i % TONES.length];
          const path = series
            .map((v, j) => `${j ? "L" : "M"}${x(j)},${y(v)}`)
            .join(" ");
          const end = series[series.length - 1];
          return (
            <g key={herd}>
              <path d={path} fill="none" stroke={tone} strokeWidth={2}
                    strokeLinejoin="round" strokeLinecap="round" />
              <circle cx={x(n - 1)} cy={y(end)} r={3} fill={tone} />
              <text
                x={PAD.left + plotW + 8}
                y={Math.min(Math.max(y(end) + 4, PAD.top + 8), PAD.top + plotH)}
                className="fill-[var(--sd-muted)] text-[10.5px]"
              >
                {herd.length > 20 ? `${herd.slice(0, 19)}…` : herd} ({Math.round(end)})
              </text>
              <title>
                {`${herd}: ${Math.round(series[0])} today, ${Math.round(end)} on ${dates[n - 1]}`}
              </title>
            </g>
          );
        })}

        <line x1={PAD.left} x2={PAD.left + plotW} y1={y(0)} y2={y(0)}
              stroke="var(--sd-line)" strokeWidth={1} />
        {[0, Math.floor((n - 1) / 2), n - 1].map((i) => (
          <text key={i} x={x(i)} y={PAD.top + plotH + 18} textAnchor="middle"
                className="fill-[var(--sd-quiet)] text-[11px]">
            {shortDate(dates[i])}
          </text>
        ))}
        <text x={PAD.left + plotW / 2} y={HERD_FLOW_HEIGHT - 4} textAnchor="middle"
              className="fill-[var(--sd-muted)] text-[11px] font-medium">
          Animals per herd
        </text>
      </svg>
    </div>
  );
}
