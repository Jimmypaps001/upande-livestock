import { useEffect, useRef, useState } from "react";
import type { DayPoint } from "@/lib/production";
import { fmt } from "@/lib/utils";

/**
 * Milk production against time, drawn by hand in SVG.
 *
 * Why not a charting library: this app has no charting dependency, and one
 * line with two axes does not earn ~400 kB of Recharts (~100 kB gzipped) in a
 * bundle a farm loads over a rural connection. The whole of this file is under
 * 200 lines and pulls in nothing. If the dashboard later grows stacked bars,
 * brushes and shared tooltips, that trade flips and Recharts should come in —
 * this is deliberately the cheap half of that decision, not a claim that
 * hand-rolled SVG scales.
 *
 * Units: kilograms. This farm records milk in kg on every Milk Recording field
 * and prices it per kg, so the axis says kg. It is NOT relabelled as litres —
 * milk is denser than water and the two numbers differ by a few percent, and
 * inventing that conversion on the client is exactly the class of mistake this
 * app refuses to make with feed units.
 */

const PAD = { top: 16, right: 20, bottom: 52, left: 72 };
/** Exported so the loading skeleton is the same height as the chart. A
 *  placeholder that guesses is a page that jumps when the data lands. */
export const MILK_CHART_HEIGHT = 320;

/** A tick ceiling a person would choose: 1, 2 or 5 times a power of ten. */
export function niceCeil(v: number): number {
  if (!(v > 0)) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / mag;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * mag;
}

/** Evenly spaced label indices, at most `max` of them, always including the
 *  last day — an axis whose right edge is unlabelled reads as truncated. */
export function tickIndices(count: number, max = 7): number[] {
  if (count <= 0) return [];
  if (count <= max) return Array.from({ length: count }, (_, i) => i);
  const step = (count - 1) / (max - 1);
  const out = new Set<number>();
  for (let i = 0; i < max; i++) out.add(Math.round(i * step));
  return [...out].sort((a, b) => a - b);
}

function shortDate(iso: string): string {
  const [, m, d] = iso.split("-");
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return `${Number(d)} ${months[Number(m) - 1] || ""}`.trim();
}

function useWidth() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(960);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const set = () => setWidth(Math.max(360, el.clientWidth));
    set();
    // The workspace is full-width now, so the chart has to redraw when the
    // sidebar collapses to icons as well as when the window resizes.
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

export function MilkChart({ points }: { points: DayPoint[] }) {
  const [ref, width] = useWidth();

  const plotW = Math.max(1, width - PAD.left - PAD.right);
  const plotH = MILK_CHART_HEIGHT - PAD.top - PAD.bottom;
  const max = niceCeil(Math.max(...points.map((p) => p.net_kg), 0) * 1.05);
  const n = points.length;

  const x = (i: number) => PAD.left + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;

  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.net_kg)}`).join(" ");
  const area = n
    ? `${line} L${x(n - 1)},${PAD.top + plotH} L${x(0)},${PAD.top + plotH} Z`
    : "";

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const xTicks = tickIndices(n);
  const total = points.reduce((s, p) => s + p.net_kg, 0);

  return (
    <div ref={ref} className="w-full">
      {n === 0 ? (
        <div className="flex h-[220px] items-center justify-center rounded-[var(--sd-radius-lg)] border border-dashed border-[var(--sd-line)] text-[13px] text-[var(--sd-quiet)]">
          No milk recorded in this window.
        </div>
      ) : (
        <svg
          width={width}
          height={MILK_CHART_HEIGHT}
          viewBox={`0 0 ${width} ${MILK_CHART_HEIGHT}`}
          role="img"
          aria-label={`Net milk in kilograms per day, ${points[0].date} to ${
            points[n - 1].date
          }. ${fmt(total)} kg in total across ${n} day${n === 1 ? "" : "s"}.`}
          className="block max-w-full"
        >
          {/* Horizontal gridlines and the y scale, in kilograms. */}
          {yTicks.map((t) => (
            <g key={t}>
              <line
                x1={PAD.left}
                x2={PAD.left + plotW}
                y1={y(t)}
                y2={y(t)}
                stroke="var(--sd-line)"
                strokeWidth={1}
              />
              <text
                x={PAD.left - 10}
                y={y(t) + 4}
                textAnchor="end"
                className="fill-[var(--sd-quiet)] text-[11px] tabular-nums"
              >
                {t >= 1000 ? `${Math.round(t / 100) / 10}k` : Math.round(t)}
              </text>
            </g>
          ))}

          <path d={area} fill="var(--sd-data-cyan)" opacity={0.12} />
          <path
            d={line}
            fill="none"
            stroke="var(--sd-data-cyan)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {points.map((p, i) => (
            <circle
              key={p.date}
              cx={x(i)}
              cy={y(p.net_kg)}
              r={n > 60 ? 1.5 : 3}
              fill="var(--sd-card)"
              stroke="var(--sd-data-cyan)"
              strokeWidth={2}
            >
              <title>
                {`${p.date} — ${fmt(p.net_kg)} kg net from ${p.sessions} milking${
                  p.sessions === 1 ? "" : "s"
                }`}
              </title>
            </circle>
          ))}

          {/* Axes. */}
          <line
            x1={PAD.left}
            x2={PAD.left + plotW}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
            stroke="var(--sd-line)"
            strokeWidth={1}
          />
          {xTicks.map((i) => (
            <text
              key={points[i].date}
              x={x(i)}
              y={PAD.top + plotH + 18}
              textAnchor="middle"
              className="fill-[var(--sd-quiet)] text-[11px]"
            >
              {shortDate(points[i].date)}
            </text>
          ))}

          {/* Axis titles — the units are stated, not implied. */}
          <text
            x={PAD.left + plotW / 2}
            y={MILK_CHART_HEIGHT - 8}
            textAnchor="middle"
            className="fill-[var(--sd-muted)] text-[11px] font-medium"
          >
            Date recorded
          </text>
          <text
            transform={`translate(16 ${PAD.top + plotH / 2}) rotate(-90)`}
            textAnchor="middle"
            className="fill-[var(--sd-muted)] text-[11px] font-medium"
          >
            Net milk (kg per day)
          </text>
        </svg>
      )}
    </div>
  );
}
