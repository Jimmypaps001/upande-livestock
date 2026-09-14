import { useEffect, useRef, useState } from "react";
import type { ProjectedItem } from "@/lib/projection";
import { URGENCY_TONE, urgencyOf } from "@/lib/projection";
import { fmt } from "@/lib/utils";

/**
 * Stock falling to nothing, one line per feed, drawn by hand in SVG.
 *
 * Why not a charting library: the same trade the milk chart made. Under 200
 * lines, no dependency, on a page a farm opens over a rural connection.
 *
 * WHY THE Y AXIS IS PER-LINE AND NOT SHARED. Silage is drawn at 3,800 kg a day
 * and mineral at 30. On one shared scale the mineral is a flat line on the
 * floor — the feed that runs out soonest becomes the one you cannot see. Each
 * line is therefore drawn as a fraction of its OWN starting stock, so what the
 * chart compares is the thing worth comparing: how fast each one is going.
 */

const PAD = { top: 16, right: 132, bottom: 44, left: 44 };
const HEIGHT = 300;

function shortDate(iso: string): string {
  const [, m, d] = iso.split("-");
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(d)} ${months[Number(m) - 1] || ""}`.trim();
}

function useWidth() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(880);
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

export function RunOutChart({
  items,
  dates,
}: {
  items: ProjectedItem[];
  dates: string[];
}) {
  const [ref, width] = useWidth();
  const plotW = Math.max(1, width - PAD.left - PAD.right);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const n = dates.length;

  const x = (i: number) => PAD.left + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (fraction: number) => PAD.top + plotH - fraction * plotH;

  const drawn = items.filter((it) => it.series.length && it.series[0] > 0).slice(0, 8);

  if (!drawn.length) {
    return (
      <div className="flex h-[220px] items-center justify-center rounded-[var(--sd-radius-lg)] border border-dashed border-[var(--sd-line)] text-[13px] text-[var(--sd-quiet)]">
        Nothing on the farm is being drawn down.
      </div>
    );
  }

  return (
    <div ref={ref} className="w-full overflow-x-auto">
      <svg
        width={width}
        height={HEIGHT}
        viewBox={`0 0 ${width} ${HEIGHT}`}
        role="img"
        aria-label={`Feed stock remaining over ${n - 1} days, as a share of what is on hand today. ${drawn
          .map((it) => `${it.item_name}: ${it.runs_out_on ? `runs out ${it.runs_out_on}` : "no run-out date"}`)
          .join("; ")}.`}
        className="block"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line x1={PAD.left} x2={PAD.left + plotW} y1={y(f)} y2={y(f)}
                  stroke="var(--sd-line)" strokeWidth={1} />
            <text x={PAD.left - 8} y={y(f) + 4} textAnchor="end"
                  className="fill-[var(--sd-quiet)] text-[11px] tabular-nums">
              {Math.round(f * 100)}%
            </text>
          </g>
        ))}

        {drawn.map((it) => {
          const start = it.series[0];
          const tone = URGENCY_TONE[urgencyOf(it)];
          const path = it.series
            .map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v / start)}`)
            .join(" ");
          // Where it hits the floor, if it does inside the window.
          const zeroAt = it.series.findIndex((v) => v <= 0);
          const labelY = y(it.series[n - 1] / start);
          return (
            <g key={it.item_code}>
              <path d={path} fill="none" stroke={tone} strokeWidth={2}
                    strokeLinejoin="round" strokeLinecap="round" />
              {zeroAt > 0 && (
                <circle cx={x(zeroAt)} cy={y(0)} r={3.5} fill={tone}>
                  <title>{`${it.item_name} runs out on ${dates[zeroAt]}`}</title>
                </circle>
              )}
              <text
                x={PAD.left + plotW + 8}
                y={Math.min(Math.max(labelY + 4, PAD.top + 8), PAD.top + plotH)}
                className="fill-[var(--sd-muted)] text-[10.5px]"
              >
                {it.item_name.length > 18 ? `${it.item_name.slice(0, 17)}…` : it.item_name}
              </text>
              <title>{`${it.item_name} — ${fmt(it.on_hand)} ${it.uom} on hand, ${fmt(it.per_day)} a day`}</title>
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
        <text x={PAD.left + plotW / 2} y={HEIGHT - 6} textAnchor="middle"
              className="fill-[var(--sd-muted)] text-[11px] font-medium">
          Share of today's stock remaining
        </text>
      </svg>
    </div>
  );
}
