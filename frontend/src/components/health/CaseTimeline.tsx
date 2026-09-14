import type { CaseEntry } from "@/lib/health";

const H = 180;
const PAD = { top: 18, right: 16, bottom: 34, left: 40 };

/** Where each recorded response sits on the vertical. Null trends are not
 *  plotted at all — an unassessed treatment is not a flat line, it is silence. */
const BANDS: { trend: number; label: string; tone: string }[] = [
  { trend: 2, label: "Resolved", tone: "var(--sd-data-green)" },
  { trend: 1, label: "Improving", tone: "var(--sd-data-cyan)" },
  { trend: 0, label: "No change", tone: "var(--sd-sev-moderate)" },
  { trend: -1, label: "Worsening", tone: "var(--sd-sev-critical)" },
];

/**
 * The course of an illness: what was given, on which day, and which way she went.
 *
 * A LIST OF FIVE TREATMENTS TELLS YOU DRUGS WERE GIVEN. The same five with
 * their days and the response written against each tells you whether she was
 * getting better, which is the question the file exists to answer — and the one
 * nobody could answer from the old screen, because the response column was on
 * the doctype and on no page at all.
 *
 * DAYS, NOT DATES, along the bottom. A course is read as "day one, day three,
 * day seven"; the calendar date is how it is filed and is on the entry beside
 * it. Gaps are drawn to scale, because four days between doses is the fact
 * somebody is trying to see.
 *
 * Treatments with no response recorded are drawn on the axis as marks without a
 * point on the line. The line only joins what was actually observed — inferring
 * a trend through silence would be drawing a recovery nobody wrote down.
 */
export function CaseTimeline({ entries }: { entries: CaseEntry[] }) {
  const dated = entries.filter((e) => e.day != null);
  if (!dated.length) {
    return (
      <p className="text-[12.5px] text-[var(--sd-muted)]">
        Nothing dated has been recorded against this file yet.
      </p>
    );
  }

  const lastDay = Math.max(...dated.map((e) => e.day as number), 1);
  const width = Math.max(300, Math.min(760, 120 + lastDay * 26));
  const plotW = width - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const x = (day: number) => PAD.left + ((day - 1) / Math.max(lastDay - 1, 1)) * plotW;
  const y = (trend: number) => PAD.top + ((2 - trend) / 3) * plotH;

  const plotted = dated.filter((e) => e.trend != null);
  const path = plotted
    .map((e, i) => `${i ? "L" : "M"}${x(e.day as number)},${y(e.trend as number)}`)
    .join(" ");

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <svg
          width={width}
          height={H}
          viewBox={`0 0 ${width} ${H}`}
          role="img"
          aria-label="Treatments and recorded response by day of the case"
        >
          {BANDS.map((b) => (
            <g key={b.trend}>
              <line
                x1={PAD.left} y1={y(b.trend)} x2={width - PAD.right} y2={y(b.trend)}
                stroke="var(--sd-line)" strokeWidth={1} strokeDasharray="2 4"
              />
              <text
                x={PAD.left - 6} y={y(b.trend) + 3}
                textAnchor="end"
                className="fill-[var(--sd-quiet)] text-[9px]"
              >
                {b.label}
              </text>
            </g>
          ))}

          {/* Every treatment gets a tick on the floor, whether or not anybody
              wrote down how she answered it. */}
          {dated.map((e, i) => (
            <line
              key={`tick-${e.name || i}`}
              x1={x(e.day as number)} y1={PAD.top - 6}
              x2={x(e.day as number)} y2={H - PAD.bottom + 6}
              stroke="var(--sd-line)" strokeWidth={1}
            />
          ))}

          {path && (
            <path
              d={path}
              fill="none"
              stroke="var(--sd-data-cyan)"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          )}

          {plotted.map((e, i) => {
            const band = BANDS.find((b) => b.trend === e.trend);
            return (
              <circle
                key={`dot-${e.name || i}`}
                cx={x(e.day as number)}
                cy={y(e.trend as number)}
                r={4.5}
                fill={band?.tone || "var(--sd-data-cyan)"}
              >
                <title>{`Day ${e.day}${e.drug ? ` · ${e.drug}` : ""} · ${e.response}`}</title>
              </circle>
            );
          })}

          {dated.map((e, i) => (
            <text
              key={`day-${e.name || i}`}
              x={x(e.day as number)}
              y={H - PAD.bottom + 20}
              textAnchor="middle"
              className="fill-[var(--sd-quiet)] text-[9.5px] tabular-nums"
            >
              {e.day}
            </text>
          ))}
          <text
            x={PAD.left} y={H - 4}
            className="fill-[var(--sd-quiet)] text-[9.5px]"
          >
            day of the case
          </text>
        </svg>
      </div>
      {!plotted.length && (
        <p className="text-[11.5px] text-[var(--sd-quiet)]">
          Marks are treatments. No response was written against any of them, so
          there is no line to draw — the file cannot say whether she improved.
        </p>
      )}
    </div>
  );
}
