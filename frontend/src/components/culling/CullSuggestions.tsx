import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronRight, Flag } from "lucide-react";
import { RowsSkeleton } from "@/components/Loading";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import { RefreshButton } from "@/components/RefreshButton";
import { isError } from "@/lib/frappe";
import {
  getCullCandidates,
  type CullBar,
  type CullCandidate,
  type CullCandidates,
  type CullYear,
} from "@/lib/culling";
import { cn } from "@/lib/utils";

/**
 * The cows the records argue against keeping, and the argument itself.
 *
 * A RANKED LIST WITH NO REASONS IS AN ORACLE, and nobody signs a disposal on
 * an oracle's say-so. So every suggestion carries the facts that put her there
 * — pregnancies lost, services that did not hold, days under treatment, the
 * gap between her calvings — drawn beside the herd she is being compared with.
 *
 * NOTHING HERE DECIDES ANYTHING. The list exists because four cows worth
 * looking at were buried under four hundred that are fine; a manager can still
 * raise a case against any animal on the farm from the tab next door, and a
 * cow on this list is not thereby condemned.
 *
 * PER-ANIMAL MILK IS NOT RECORDED ON THIS FARM. Milk Recording is a herd and a
 * session, so "low produce" cannot honestly mean litres. It means the milk a
 * health case cost her where somebody wrote the figure down, and the interval
 * between her calvings — which is what the farm actually gets out of her.
 */
export function CullSuggestions({
  onPick,
}: {
  /** Take her to the raise form with her already chosen. */
  onPick: (animal: string) => void;
}) {
  const [data, setData] = useState<CullCandidates | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    const r = await getCullCandidates();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setData(r);
    setOpen((current) => current ?? r.candidates[0]?.animal ?? null);
  }

  useEffect(() => {
    void load();
  }, []);

  const worst = data?.candidates[0]?.score ?? 1;

  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Worth a look</CardTitle>
          <CardDescription>
            {data
              ? `${data.flagged_count} of ${data.considered} cows have something on their record worth reading. The ${data.candidates.length} with the strongest case are here.`
              : "Ranked by what is on their records, worst first."}
          </CardDescription>
        </CardHeading>
        <CardTools>
          <RefreshButton onClick={load} loading={loading} label="the ranking" />
        </CardTools>
      </CardHeaderRow>
      <CardContent className="flex flex-col gap-3 pt-0">
        {failure && (
          <p className="text-[13px] text-[var(--sd-sev-critical)]">{failure}</p>
        )}

        {!data ? (
          <RowsSkeleton rows={5} />
        ) : !data.candidates.length ? (
          <p className="text-[13px] text-[var(--sd-muted)]">
            Nothing stands out. No cow on the farm is losing pregnancies, failing
            to hold, or spending long enough under treatment to be worth raising.
          </p>
        ) : (
          <ul className="flex max-h-[min(66vh,640px)] flex-col gap-1.5 overflow-y-auto">
            {data.candidates.map((c) => (
              <li key={c.animal}>
                <button
                  type="button"
                  onClick={() => setOpen(open === c.animal ? null : c.animal)}
                  aria-expanded={open === c.animal}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-colors",
                    open === c.animal
                      ? "bg-[var(--sd-bg-soft)]"
                      : "hover:bg-[var(--sd-bg-soft)]",
                  )}
                >
                  <ChevronRight
                    className={cn(
                      "h-4 w-4 shrink-0 text-[var(--sd-quiet)] transition-transform",
                      open === c.animal && "rotate-90",
                    )}
                  />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                      {c.name}
                      <span className="ml-2 font-normal text-[11.5px] text-[var(--sd-quiet)]">
                        {c.herd || "no herd"}
                      </span>
                    </span>
                    <span className="truncate text-[11.5px] text-[var(--sd-muted)]">
                      {c.reasons.map((r) => r.label).join(" · ")}
                    </span>
                  </span>
                  <ScoreBar score={c.score} worst={worst} />
                </button>

                {open === c.animal && <Detail c={c} onPick={onPick} />}
              </li>
            ))}
          </ul>
        )}

        {data && !data.per_animal_milk && (
          <p className="border-t border-[var(--sd-line)] pt-3 text-[11.5px] leading-relaxed text-[var(--sd-quiet)]">
            Milk is recorded per herd per session on this farm, not per cow, so
            no ranking here is based on litres. What stands in for it is the
            interval between her calvings and the milk a health case is recorded
            as having cost her.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** How strong her case is relative to the strongest on the list. */
function ScoreBar({ score, worst }: { score: number; worst: number }) {
  const share = Math.max(0.08, Math.min(1, score / Math.max(worst, 1)));
  return (
    <span className="flex shrink-0 items-center gap-2" aria-label={`Case strength ${score}`}>
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--sd-line)]">
        <span
          className="block h-full rounded-full bg-[var(--sd-sev-critical)]"
          style={{ width: `${share * 100}%` }}
        />
      </span>
      <span className="w-6 text-right text-[11.5px] tabular-nums text-[var(--sd-quiet)]">
        {score}
      </span>
    </span>
  );
}

function Detail({ c, onPick }: { c: CullCandidate; onPick: (animal: string) => void }) {
  return (
    <div className="mb-2 ml-7 mt-1 flex flex-col gap-4 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-4 shadow-[var(--sd-shadow-inset)]">
      <ul className="flex flex-col gap-1.5">
        {c.reasons.map((r) => (
          <li key={r.key} className="flex items-start gap-2 text-[12.5px] leading-snug">
            <AlertTriangle
              className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--sd-sev-moderate)]"
              strokeWidth={2}
            />
            <span>
              <span className="font-medium text-[var(--sd-ink)]">{r.label}</span>
              <span className="text-[var(--sd-muted)]"> — {r.detail}</span>
            </span>
          </li>
        ))}
      </ul>

      {!!c.bars.length && <Bars bars={c.bars} />}
      <Years years={c.years} />

      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="outline" onClick={() => onPick(c.animal)}>
          <Flag className="mr-1.5 h-3.5 w-3.5" strokeWidth={2} />
          Open a case on her
        </Button>
        <span className="text-[11.5px] text-[var(--sd-quiet)]">
          Nothing here culls her. It says what her record says.
        </span>
      </div>
    </div>
  );
}

const BAR_ROW = 30;

/**
 * Her figure against the herd's, one pair of bars per measure.
 *
 * Each measure gets its OWN scale. Days ill and days open are both days and
 * both a number nobody wants large, but 200 days ill beside 140 days open on
 * one axis says they are comparable quantities, and they are not.
 */
function Bars({ bars }: { bars: CullBar[] }) {
  const width = 260;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
        Her, against the herd
      </p>
      <div className="flex flex-col gap-2.5">
        {bars.map((b) => {
          const top = Math.max(b.hers, b.herd, 1);
          return (
            <div key={b.label} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="w-[136px] shrink-0 text-[12px] text-[var(--sd-muted)]">
                {b.label}
              </span>
              <svg
                width={width}
                height={BAR_ROW}
                viewBox={`0 0 ${width} ${BAR_ROW}`}
                className="max-w-full"
                role="img"
                aria-label={`${b.label}: hers ${b.hers}${b.unit}, the herd ${b.herd}${b.unit}`}
              >
                <rect
                  x={0} y={2} rx={3}
                  width={Math.max(2, (b.hers / top) * (width - 46))}
                  height={11}
                  fill={b.worse ? "var(--sd-sev-critical)" : "var(--sd-data-green)"}
                />
                <rect
                  x={0} y={16} rx={3}
                  width={Math.max(2, (b.herd / top) * (width - 46))}
                  height={11}
                  fill="var(--sd-line)"
                />
                <text
                  x={width - 42} y={11}
                  className="fill-[var(--sd-ink)] text-[10px] tabular-nums"
                >
                  {b.hers}
                  {b.unit}
                </text>
                <text
                  x={width - 42} y={25}
                  className="fill-[var(--sd-quiet)] text-[10px] tabular-nums"
                >
                  {b.herd}
                  {b.unit}
                </text>
              </svg>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-[var(--sd-quiet)]">
        Top bar is hers, bottom is the herd's median. Higher is worse on all of them.
      </p>
    </div>
  );
}

const YEAR_H = 96;

/**
 * Her last five years: what she produced and what she cost.
 *
 * Calvings above the line, losses and illness below it. A cow whose record is
 * three calvings and nothing else looks completely different at a glance from
 * one whose record is two abortions and four months under treatment, and the
 * glance is the whole reason to draw it.
 */
function Years({ years }: { years: CullYear[] }) {
  const sickTop = Math.max(...years.map((y) => y.sick_days), 30);
  const evTop = Math.max(...years.map((y) => Math.max(y.calvings, y.abortions, y.services)), 2);
  const colW = 52;
  const width = years.length * colW;
  const mid = YEAR_H / 2;

  const anything = useMemo(
    () => years.some((y) => y.calvings || y.abortions || y.services || y.sick_days),
    [years],
  );
  if (!anything) {
    return (
      <p className="text-[11.5px] text-[var(--sd-quiet)]">
        Nothing is recorded against her in the last five years beyond what is listed above.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
        Her last five years
      </p>
      <div className="overflow-x-auto">
        <svg
          width={width}
          height={YEAR_H + 18}
          viewBox={`0 0 ${width} ${YEAR_H + 18}`}
          role="img"
          aria-label="Calvings, services, losses and days ill by year"
        >
          <line
            x1={0} y1={mid} x2={width} y2={mid}
            stroke="var(--sd-line)" strokeWidth={1}
          />
          {years.map((y, i) => {
            const x = i * colW;
            const barW = 9;
            const up = (n: number) => (n / evTop) * (mid - 10);
            return (
              <g key={y.year}>
                {/* what she produced — above the line */}
                <rect
                  x={x + 6} y={mid - up(y.calvings)} width={barW}
                  height={Math.max(y.calvings ? 2 : 0, up(y.calvings))}
                  rx={2} fill="var(--sd-data-green)"
                />
                <rect
                  x={x + 17} y={mid - up(y.services)} width={barW}
                  height={Math.max(y.services ? 2 : 0, up(y.services))}
                  rx={2} fill="var(--sd-data-cyan)"
                />
                {/* what she cost — below it */}
                <rect
                  x={x + 6} y={mid} width={barW}
                  height={Math.max(y.abortions ? 2 : 0, up(y.abortions))}
                  rx={2} fill="var(--sd-sev-critical)"
                />
                <rect
                  x={x + 17} y={mid} width={barW}
                  height={Math.max(
                    y.sick_days ? 2 : 0,
                    (y.sick_days / sickTop) * (mid - 10),
                  )}
                  rx={2} fill="var(--sd-sev-moderate)"
                />
                <text
                  x={x + 22} y={YEAR_H + 12}
                  textAnchor="middle"
                  className="fill-[var(--sd-quiet)] text-[10px] tabular-nums"
                >
                  {String(y.year).slice(2)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--sd-quiet)]">
        <Key tone="var(--sd-data-green)" label="Calvings" />
        <Key tone="var(--sd-data-cyan)" label="Services" />
        <Key tone="var(--sd-sev-critical)" label="Losses" />
        <Key tone="var(--sd-sev-moderate)" label="Days ill" />
      </div>
    </div>
  );
}

function Key({ tone, label }: { tone: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-[2px]" style={{ background: tone }} />
      {label}
    </span>
  );
}
