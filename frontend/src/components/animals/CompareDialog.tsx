import { useMemo, useState } from "react";
import { Check, Plus, ShieldAlert, X } from "lucide-react";
import { axesFrom } from "@/components/animals/KpiRadar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/feeding/Notice";
import { STAGES, initialsOf, type AnimalProfile, type AnimalSummary } from "@/lib/animals";
import { cn } from "@/lib/utils";

/**
 * Two or three cows, and the farm's middle cow, on one set of axes.
 *
 * Comparison is what a cull decision actually is. Nobody looks at a conception
 * rate of 44% and knows what to do with it; they know when they can see it
 * against the herd she is standing in. So the farm's median is always drawn,
 * whether or not another animal is picked — an animal alone on this chart
 * would be the same number in a different shape.
 *
 * MEDIAN, NOT MEAN, and the benchmark is a dashed outline rather than a filled
 * shape: it is a reference, not a competitor, and filling it would make the
 * farm look like a fourth cow.
 */

const SIZE = 320;
const C = SIZE / 2;
const R = 112;
const RINGS = 4;
/** Room outside the drawing for the axis labels. */
const LABEL_PAD = 46;

/** Up to three. A fourth outline turns the chart into a scribble, and nobody
 *  compares four cows at once — they compare a shortlist. */
const MAX = 3;

const LINES = ["var(--sd-ink)", "var(--sd-data-cyan)", "var(--sd-data-amber)"];

function point(i: number, count: number, radius: number) {
  const a = ((i / count) * 2 * Math.PI) - Math.PI / 2;
  return { x: C + radius * Math.cos(a), y: C + radius * Math.sin(a) };
}

function polygon(values: (number | null)[], count: number) {
  return values
    .map((v, i) => {
      const p = point(i, count, R * (v ?? 0));
      return `${p.x},${p.y}`;
    })
    .join(" ");
}

export function CompareDialog({
  open,
  onOpenChange,
  subject,
  herd,
  profileFor,
  benchmark,
  onMarkCull,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  subject: AnimalProfile;
  herd: AnimalSummary[];
  /** Her full profile if it has arrived. Null while it is still being
   *  fetched — a comparison of two cows is two trips to the server, and the
   *  dialog draws what it has rather than blocking on the slowest one. */
  profileFor: (a: AnimalSummary) => AnimalProfile | null;
  /** The farm's middle cow, 0–1 per axis, in the same order axesFrom returns. */
  benchmark: number[];
  onMarkCull: (reason: string) => Promise<void> | void;
}) {
  const [others, setOthers] = useState<AnimalSummary[]>([]);
  const [term, setTerm] = useState("");
  const [marking, setMarking] = useState(false);
  const [marked, setMarked] = useState(false);

  const cohort = useMemo(
    () =>
      [subject, ...others.map(profileFor)]
        .filter((a): a is AnimalProfile => !!a)
        .slice(0, MAX),
    [subject, others, profileFor],
  );
  const axes = useMemo(() => cohort.map((a) => axesFrom(a.kpis)), [cohort]);
  const labels = axes[0] ?? [];
  const n = labels.length;

  /** How many axes the subject sits below the farm's middle cow on. */
  const below = useMemo(() => {
    const mine = axes[0] ?? [];
    return mine.reduce((count, axis, i) => {
      if (axis.value == null) return count;
      return axis.value < (benchmark[i] ?? 0) ? count + 1 : count;
    }, 0);
  }, [axes, benchmark]);

  const measured = (axes[0] ?? []).filter((a) => a.value != null).length;
  const suggestCull = measured >= 4 && below > measured / 2;

  const reason = useMemo(() => {
    const mine = axes[0] ?? [];
    const weak = mine
      .filter((a, i) => a.value != null && a.value < (benchmark[i] ?? 0))
      .map((a) => a.label.toLowerCase());
    return `Below the herd median on ${weak.join(", ")}.`;
  }, [axes, benchmark]);

  const pool = useMemo(() => {
    const taken = new Set([subject.id, ...others.map((o) => o.id)]);
    const q = term.trim().toLowerCase();
    return herd
      .filter((a) => !taken.has(a.id))
      .filter((a) => !q || [a.id, a.name, a.herd].some((f) => f.toLowerCase().includes(q)))
      .slice(0, 6);
  }, [herd, others, subject.id, term]);

  async function mark() {
    setMarking(true);
    await onMarkCull(reason);
    setMarking(false);
    setMarked(true);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[94vh] w-[min(1240px,96vw)] max-w-none overflow-y-auto">
        <DialogHeader>
          <DialogTitle>How {subject.name} compares</DialogTitle>
          <DialogDescription>
            Against the farm&apos;s middle cow, and up to two others. Outward is better
            on every axis.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-7 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
          <div className="flex flex-col gap-4">
            {/* The viewBox is wider than the drawing on purpose: the axis
                labels sit outside the outer ring, and "INTERVAL" set from the
                right-hand vertex runs past SIZE and gets clipped. Padding the
                box rather than shrinking the chart keeps the rings the size
                they want to be. */}
            <svg
              viewBox={`${-LABEL_PAD} 0 ${SIZE + LABEL_PAD * 2} ${SIZE}`}
              className="w-full"
              role="img"
              aria-label="Comparison"
            >
              {Array.from({ length: RINGS }, (_, r) => (
                <polygon
                  key={r}
                  points={Array.from({ length: n }, (_, i) => {
                    const p = point(i, n, (R * (r + 1)) / RINGS);
                    return `${p.x},${p.y}`;
                  }).join(" ")}
                  fill="none"
                  stroke="var(--sd-line-soft)"
                />
              ))}
              {Array.from({ length: n }, (_, i) => {
                const p = point(i, n, R);
                return <line key={i} x1={C} y1={C} x2={p.x} y2={p.y} stroke="var(--sd-line-soft)" />;
              })}

              {/* the farm: a reference, so an outline rather than a shape */}
              <polygon
                points={polygon(benchmark.slice(0, n), n)}
                fill="none"
                stroke="var(--sd-quiet)"
                strokeWidth={1.5}
                strokeDasharray="5 4"
              />

              {cohort.map((a, ci) => (
                <polygon
                  key={a.id}
                  points={polygon(axes[ci].map((x) => x.value), n)}
                  fill={LINES[ci]}
                  fillOpacity={ci === 0 ? 0.12 : 0.07}
                  stroke={LINES[ci]}
                  strokeWidth={ci === 0 ? 2 : 1.5}
                  strokeLinejoin="round"
                />
              ))}

              {labels.map((a, i) => {
                const p = point(i, n, R + 22);
                return (
                  <text
                    key={a.key}
                    x={p.x}
                    y={p.y}
                    textAnchor={p.x > C + 4 ? "start" : p.x < C - 4 ? "end" : "middle"}
                    dominantBaseline="middle"
                    className="fill-[var(--sd-quiet)] text-[9.5px] font-medium uppercase"
                    style={{ letterSpacing: "0.1em" }}
                  >
                    {a.label}
                  </text>
                );
              })}
            </svg>

            <ul className="flex flex-col gap-1.5">
              {cohort.map((a, ci) => (
                <li key={a.id} className="flex items-center gap-2.5 text-[12.5px]">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: LINES[ci] }} />
                  <span className="font-medium text-[var(--sd-ink)]">{a.name}</span>
                  <span className="tabular-nums text-[var(--sd-quiet)]">{a.id}</span>
                  {ci > 0 && (
                    <button
                      type="button"
                      onClick={() => setOthers((o) => o.filter((x) => x.id !== a.id))}
                      className="ml-auto text-[var(--sd-quiet)] transition-colors hover:text-[var(--sd-ink)]"
                      aria-label={`Remove ${a.name} from the comparison`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </li>
              ))}
              <li className="flex items-center gap-2.5 text-[12.5px] text-[var(--sd-muted)]">
                <span className="h-0 w-2.5 border-t-2 border-dashed border-[var(--sd-quiet)]" />
                The farm&apos;s middle cow
              </li>
            </ul>
          </div>

          <div className="flex min-w-0 flex-col gap-4">
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-[var(--sd-line)] text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
                  <th className="py-2 pr-3">Measure</th>
                  {cohort.map((a) => (
                    <th key={a.id} className="py-2 pr-3 text-right">{a.name}</th>
                  ))}
                  <th className="py-2 text-right">Farm</th>
                </tr>
              </thead>
              <tbody>
                {labels.map((axis, i) => (
                  <tr key={axis.key} className="border-b border-[var(--sd-line-soft)] last:border-0">
                    <td className="py-2 pr-3 text-[var(--sd-muted)]">{axis.label}</td>
                    {cohort.map((a, ci) => {
                      const cell = axes[ci][i];
                      const under = cell.value != null && cell.value < (benchmark[i] ?? 0);
                      return (
                        <td
                          key={a.id}
                          className={cn(
                            "py-2 pr-3 text-right tabular-nums",
                            under ? "text-[var(--sd-sev-critical)]" : "text-[var(--sd-ink)]",
                          )}
                        >
                          {cell.readout}
                        </td>
                      );
                    })}
                    <td className="py-2 text-right tabular-nums text-[var(--sd-quiet)]">
                      {Math.round((benchmark[i] ?? 0) * 100)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {others.length < MAX - 1 && (
              <div className="flex flex-col gap-2">
                <label className="text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
                  Add another
                </label>
                <Input
                  value={term}
                  onChange={(e) => setTerm(e.target.value)}
                  placeholder="Number, name or herd…"
                  className="h-9 text-[13px]"
                />
                <div className="flex flex-wrap gap-1.5">
                  {pool.map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => {
                        setOthers((o) => [...o, a]);
                        setTerm("");
                      }}
                      className="inline-flex items-center gap-1.5 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] px-2.5 py-1 text-[12px] text-[var(--sd-ink)] transition-colors hover:bg-[var(--sd-pistachio)]"
                    >
                      <span
                        className="flex h-4 w-4 items-center justify-center rounded-full text-[8px] font-semibold text-white"
                        style={{ background: STAGES[a.stage].tone }}
                      >
                        {initialsOf(a.name, a.id)}
                      </span>
                      {a.name}
                      <Plus className="h-3 w-3 text-[var(--sd-quiet)]" />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {suggestCull && !marked && (
              <Notice tone="error">
                <span className="flex flex-col gap-2">
                  <span className="inline-flex items-center gap-2 font-medium">
                    <ShieldAlert className="h-4 w-4" />
                    {subject.name} is below the herd on {below} of {measured} measures.
                  </span>
                  <span className="text-[12.5px]">
                    Worth reviewing. Marking her records that judgement and puts it in her
                    timeline — she keeps her herd, her place in the head count and her
                    ration until somebody actually disposes of her.
                  </span>
                  <span>
                    <Button size="sm" onClick={mark} disabled={marking}>
                      {marking ? "Marking…" : "Mark for cull review"}
                    </Button>
                  </span>
                </span>
              </Notice>
            )}

            {marked && (
              <Notice tone="ok">
                <span className="inline-flex items-center gap-2">
                  <Check className="h-4 w-4" />
                  {subject.name} is marked for review, with the case above recorded
                  against her.
                </span>
              </Notice>
            )}

            {!suggestCull && measured >= 4 && (
              <p className="text-[12.5px] text-[var(--sd-muted)]">
                {subject.name} holds her own — below the herd on {below} of {measured}{" "}
                measures. Nothing to raise.
              </p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
