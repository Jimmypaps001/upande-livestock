import { useEffect, useMemo, useRef, useState } from "react";
import { formatMetric, METRICS, shown, type FeedQuality, type Metric } from "@/lib/feed-quality";

/**
 * One quality figure, week by week, one line per milking herd.
 *
 * One measure at a time on one axis — fat and SCC are different scales, and
 * two y-axes on one chart invite a comparison the data does not make. Lines
 * carry their herd's colour and a label at their end, so identity is never
 * colour alone; the legend sits above. Hovering a week shows every herd's
 * figure for it.
 *
 * Colours are the app's data hues (indigo, cyan, pink), checked for
 * colour-blind separation; green and amber stay with status (posted/waiting).
 */

export const HERD_COLOURS = ["var(--sd-data-indigo)", "var(--sd-data-cyan)", "var(--sd-data-pink)", "var(--sd-data-purple)"];

const HEIGHT = 300;
const PAD = { top: 16, right: 184, bottom: 40, left: 56 };

function useWidth() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(900);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const set = () => setWidth(Math.max(360, el.clientWidth));
    set();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Round outward to a step a person would pick. */
function niceRange(lo: number, hi: number): [number, number, number] {
  const span = Math.max(hi - lo, 1e-6);
  const raw = span / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step, step];
}

function shortWeek(iso: string) {
  const [, m, d] = iso.split("-");
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(d)} ${months[Number(m) - 1] ?? ""}`;
}

export function QualityTrendChart({ data, metric }: { data: FeedQuality; metric: Metric }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const herds = data.herds.map((h) => h.herd);
  const weeks = data.weeks;

  const { lo, hi, step } = useMemo(() => {
    const vals = weeks.flatMap((w) => herds.map((h) => shown(metric, w.herds[h]?.[metric]))).filter(
      (v): v is number => v != null,
    );
    if (!vals.length) return { lo: 0, hi: 1, step: 0.25 };
    const [a, b, s] = niceRange(Math.min(...vals), Math.max(...vals));
    return { lo: a, hi: b, step: s };
  }, [weeks, herds, metric]);

  const plotW = width - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (weeks.length <= 1 ? plotW / 2 : (i / (weeks.length - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - ((v - lo) / (hi - lo || 1)) * plotH;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toFixed(6)));
  const labelEvery = Math.max(1, Math.ceil(weeks.length / 8));

  const lines = herds.map((h, k) => {
    const pts = weeks
      .map((w, i) => ({ i, v: shown(metric, w.herds[h]?.[metric]) }))
      .filter((p): p is { i: number; v: number } => p.v != null);
    const d = pts.map((p, n) => `${n ? "L" : "M"}${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
    return { herd: h, colour: HERD_COLOURS[k % HERD_COLOURS.length], pts, d, last: pts[pts.length - 1] };
  });

  // End labels, nudged apart so two herds ending close together stay readable.
  const ends = lines
    .filter((l) => l.last)
    .map((l) => ({ herd: l.herd, y: y(l.last!.v), v: l.last!.v }))
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;

  function onMove(e: React.MouseEvent<SVGRectElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * plotW;
    const i = Math.round((px / (plotW || 1)) * (weeks.length - 1));
    setHover(Math.min(weeks.length - 1, Math.max(0, i)));
  }

  const m = METRICS[metric];
  const hw = hover != null ? weeks[hover] : null;

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-[var(--sd-text)]" aria-label="Herds">
        {lines.map((l) => (
          <li key={l.herd} className="flex items-center gap-2">
            <span aria-hidden className="h-[2px] w-4 rounded-full" style={{ background: l.colour }} />
            {l.herd}
          </li>
        ))}
      </ul>
      <div ref={ref} className="relative w-full">
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={`${m.label} by week, one line per milking herd`}
          className="block"
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={PAD.left + plotW} y1={y(t)} y2={y(t)} stroke="var(--sd-line)" strokeWidth={1} />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--sd-quiet)">
                {metric === "scc" ? `${Math.round(t)}k` : `${t.toFixed(step < 0.1 ? 2 : 1)}%`}
              </text>
            </g>
          ))}
          {weeks.map((w, i) =>
            i % labelEvery === 0 ? (
              <text key={w.week} x={x(i)} y={HEIGHT - PAD.bottom + 18} textAnchor="middle" fontSize={11} fill="var(--sd-quiet)">
                {shortWeek(w.week)}
              </text>
            ) : null,
          )}
          <text x={PAD.left + plotW / 2} y={HEIGHT - 4} textAnchor="middle" fontSize={11} fill="var(--sd-quiet)">
            Week starting
          </text>
          {hover != null && (
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--sd-muted)" strokeWidth={1} strokeDasharray="3 3" />
          )}
          {lines.map((l) => (
            <path key={l.herd} d={l.d} fill="none" stroke={l.colour} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {hover != null &&
            lines.map((l) => {
              const p = l.pts.find((q) => q.i === hover);
              return p ? (
                <circle key={l.herd} cx={x(p.i)} cy={y(p.v)} r={4.5} fill={l.colour} stroke="var(--sd-card)" strokeWidth={2} />
              ) : null;
            })}
          {ends.map((e) => {
            const l = lines.find((q) => q.herd === e.herd)!;
            return (
              <g key={e.herd}>
                <circle cx={x(l.last!.i)} cy={y(l.last!.v)} r={3} fill={l.colour} />
                <text x={PAD.left + plotW + 8} y={e.y} dy="0.32em" fontSize={11.5} fill="var(--sd-text)">
                  {formatMetric(metric, metric === "scc" ? e.v * 1000 : e.v)}{" "}
                  <tspan fill="var(--sd-quiet)">{e.herd.length > 18 ? `${e.herd.slice(0, 17).trimEnd()}…` : e.herd}</tspan>
                </text>
              </g>
            );
          })}
          <rect
            x={PAD.left}
            y={PAD.top}
            width={Math.max(plotW, 1)}
            height={plotH}
            fill="transparent"
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
          />
        </svg>
        {hw && (
          <div
            role="tooltip"
            className="pointer-events-none absolute top-2 z-10 min-w-[12rem] rounded-md border border-[var(--sd-line)] bg-[var(--sd-card)] px-3 py-2 text-[12px] shadow-[var(--sd-shadow-2)]"
            style={{ left: Math.min(Math.max(x(hover!) + 12, 0), width - 210) }}
          >
            <div className="mb-1 font-medium text-[var(--sd-ink)]">Week of {shortWeek(hw.week)}</div>
            {lines.map((l) => (
              <div key={l.herd} className="flex items-center justify-between gap-4 text-[var(--sd-text)]">
                <span className="flex items-center gap-1.5">
                  <span aria-hidden className="size-2 rounded-full" style={{ background: l.colour }} />
                  {l.herd}
                </span>
                <span className="tabular-nums">{formatMetric(metric, hw.herds[l.herd]?.[metric])}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
