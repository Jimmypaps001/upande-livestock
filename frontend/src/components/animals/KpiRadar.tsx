import type { AnimalKpis } from "@/lib/animals";

/**
 * Six measures of a cow, on one shape.
 *
 * The point of a radar here is not the numbers — they are listed underneath,
 * where they can be read exactly. It is the silhouette: a cow who is strong on
 * yield and weak on fertility makes a lopsided shape you recognise across the
 * herd, and two animals compared side by side are compared as shapes before
 * anybody reads a figure.
 *
 * EVERY AXIS RUNS THE SAME WAY: outward is better. Two of the underlying
 * measures do not — a shorter calving interval and fewer treatments are the
 * good end — so they are inverted here rather than left to trip up the reader.
 * A radar with one axis running backwards is worse than no radar.
 *
 * Drawn by hand, as the milk chart and the cycle ring are.
 */

const SIZE = 230;
const C = SIZE / 2;
const R = 78;
const RINGS = 3;
/** Room outside the drawing for the axis labels, which sit past the outer
 *  ring and would otherwise be clipped by the viewBox. */
const LABEL_PAD = 40;

export interface RadarAxis {
  key: string;
  label: string;
  /** 0–1, outward is better. Null when she has no history for it yet. */
  value: number | null;
  /** What the number actually is, for the list underneath. */
  readout: string;
}

/** Turn the raw KPIs into six comparable axes. */
export function axesFrom(k: AnimalKpis): RadarAxis[] {
  const clamp = (n: number) => Math.max(0, Math.min(1, n));
  return [
    {
      key: "fertility",
      label: "Fertility",
      value: k.conceptionRate == null ? null : clamp(k.conceptionRate / 100),
      readout: k.conceptionRate == null ? "—" : `${k.conceptionRate}% conception`,
    },
    {
      key: "yield",
      label: "Yield",
      // 100 is the herd median; 150 and above fills the axis.
      value: k.yieldIndex == null ? null : clamp((k.yieldIndex - 50) / 100),
      readout: k.yieldIndex == null ? "—" : `${k.yieldIndex}% of herd median`,
    },
    {
      key: "interval",
      label: "Interval",
      // Inverted: 365 days is ideal, 480 is poor.
      value: k.calvingInterval == null ? null : clamp((480 - k.calvingInterval) / 115),
      readout: k.calvingInterval == null ? "—" : `${k.calvingInterval} days between calvings`,
    },
    {
      key: "longevity",
      label: "Longevity",
      value: clamp(k.parity / 6),
      readout: `${k.parity} ${k.parity === 1 ? "calving" : "calvings"}`,
    },
    {
      key: "health",
      label: "Health",
      // Inverted: no treatments fills the axis, four or more empties it.
      value: clamp((4 - k.treatments) / 4),
      readout: `${k.treatments} ${k.treatments === 1 ? "treatment" : "treatments"} this year`,
    },
    {
      key: "carried",
      label: "Carried",
      value: k.conceptions === 0 ? null : clamp((k.conceptions - k.abortions) / Math.max(1, k.conceptions)),
      readout:
        k.conceptions === 0
          ? "—"
          : `${k.conceptions - k.abortions} of ${k.conceptions} carried to term`,
    },
  ];
}

function point(i: number, count: number, radius: number) {
  const a = ((i / count) * 2 * Math.PI) - Math.PI / 2;
  return { x: C + radius * Math.cos(a), y: C + radius * Math.sin(a) };
}

export function KpiRadar({ kpis }: { kpis: AnimalKpis }) {
  const axes = axesFrom(kpis);
  const n = axes.length;
  const known = axes.filter((a) => a.value != null).length;

  const shape = axes
    .map((a, i) => {
      // An axis with no history is drawn at the centre rather than skipped, so
      // the shape does not silently gain a straight edge that reads as a score.
      const p = point(i, n, R * (a.value ?? 0));
      return `${p.x},${p.y}`;
    })
    .join(" ");

  return (
    <div className="flex flex-col gap-4">
      <svg
        viewBox={`${-LABEL_PAD} 0 ${SIZE + LABEL_PAD * 2} ${SIZE}`}
        className="h-[200px] w-full"
        role="img"
        aria-label="Animal performance"
      >
        {Array.from({ length: RINGS }, (_, r) => {
          const radius = (R * (r + 1)) / RINGS;
          return (
            <polygon
              key={r}
              points={Array.from({ length: n }, (_, i) => {
                const p = point(i, n, radius);
                return `${p.x},${p.y}`;
              }).join(" ")}
              fill="none"
              stroke="var(--sd-line-soft)"
              strokeWidth={1}
            />
          );
        })}
        {axes.map((_, i) => {
          const p = point(i, n, R);
          return <line key={i} x1={C} y1={C} x2={p.x} y2={p.y} stroke="var(--sd-line-soft)" strokeWidth={1} />;
        })}

        {known > 0 && (
          <polygon
            points={shape}
            fill="var(--sd-ink)"
            fillOpacity={0.1}
            stroke="var(--sd-ink)"
            strokeWidth={1.75}
            strokeLinejoin="round"
          />
        )}
        {axes.map((a, i) => {
          if (a.value == null) return null;
          const p = point(i, n, R * a.value);
          return <circle key={a.key} cx={p.x} cy={p.y} r={3} fill="var(--sd-ink)" />;
        })}

        {axes.map((a, i) => {
          const p = point(i, n, R + 21);
          return (
            <text
              key={a.key}
              x={p.x}
              y={p.y}
              textAnchor={p.x > C + 4 ? "start" : p.x < C - 4 ? "end" : "middle"}
              dominantBaseline="middle"
              className="fill-[var(--sd-quiet)] text-[9px] font-medium uppercase"
              style={{ letterSpacing: "0.1em" }}
            >
              {a.label}
            </text>
          );
        })}
      </svg>

      <dl className="flex flex-col gap-1.5">
        {axes.map((a) => (
          <div key={a.key} className="flex items-baseline justify-between gap-3">
            <dt className="text-[12px] text-[var(--sd-muted)]">{a.label}</dt>
            <dd className="truncate text-right text-[12px] tabular-nums text-[var(--sd-ink)]">
              {a.readout}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
