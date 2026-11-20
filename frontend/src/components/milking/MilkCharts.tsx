import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Notice } from "@/components/feeding/Notice";
import { RefreshButton } from "@/components/RefreshButton";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { isError } from "@/lib/frappe";
import {
  colourFor,
  fetchMilkByHerd,
  fetchQualityTrend,
  niceRange,
  orderHerds,
  PERIODS,
  seriesValues,
  type MilkByHerd,
  type QualityPoint,
} from "@/lib/milk-charts";
import { cn } from "@/lib/utils";

/**
 * The Milking dashboard: milk yield by herd, and the lab's quality figures.
 *
 * Hand-drawn SVG like the rest of the app's charts, on its theme tokens, so
 * light and dark both read. A line carries its herd's name at the end as well as
 * its colour, so identity is never colour alone; pass/fail markers differ in
 * shape (circle / cross), not only in hue.
 */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const shortDay = (iso: string) => {
  const [, m, d] = iso.split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1] ?? ""}`;
};

function useWidth() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(900);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const set = () => setWidth(Math.max(320, el.clientWidth));
    set();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

function Pill({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        "h-7 rounded-full border px-3 text-[12px] font-medium transition-colors",
        on
          ? "border-[var(--sd-ink)] bg-[var(--sd-ink)] text-white"
          : "border-[var(--sd-line)] text-[var(--sd-muted)] hover:bg-[var(--sd-bg-soft)]",
      )}
    >
      {children}
    </button>
  );
}

function Periods({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="flex gap-1.5" role="group" aria-label="Period">
      {PERIODS.map((p) => (
        <Pill key={p} on={value === p} onClick={() => onChange(p)}>
          {p} days
        </Pill>
      ))}
    </div>
  );
}

const HEIGHT = 280;
const PAD = { top: 14, right: 20, bottom: 36, left: 52 };

function Axes({
  width, ticks, y, days, plotW, plotH, fmt,
}: {
  width: number; ticks: number[]; y: (v: number) => number; days: string[]; plotW: number; plotH: number;
  fmt: (v: number) => string;
}) {
  const every = Math.max(1, Math.ceil(days.length / 7));
  const x = (i: number) => PAD.left + (days.length <= 1 ? plotW / 2 : (i / (days.length - 1)) * plotW);
  return (
    <>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--sd-line)" strokeWidth={1} />
          <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--sd-quiet)">
            {fmt(t)}
          </text>
        </g>
      ))}
      {days.map((d, i) =>
        i % every === 0 ? (
          <text key={d} x={x(i)} y={PAD.top + plotH + 18} textAnchor="middle" fontSize={11} fill="var(--sd-quiet)">
            {shortDay(d)}
          </text>
        ) : null,
      )}
    </>
  );
}

/** Yield per day, one line per herd. */
export function YieldChart({ data, perCow }: { data: MilkByHerd; perCow: boolean }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const herds = useMemo(() => orderHerds(data.herds), [data.herds]);
  const days = data.days;
  const plotW = width - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;

  const { lo, hi, step } = useMemo(() => {
    const vals = herds.flatMap((h) => seriesValues(h, perCow)).filter((v): v is number => v != null);
    if (!vals.length) return { lo: 0, hi: 1, step: 0.25 };
    const [, b, s] = niceRange(0, Math.max(...vals));
    return { lo: 0, hi: b, step: s };
  }, [herds, perCow]);

  const x = (i: number) => PAD.left + (days.length <= 1 ? plotW / 2 : (i / (days.length - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - ((v - lo) / (hi - lo || 1)) * plotH;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toFixed(6)));

  const lines = herds.map((h, k) => {
    const vals = seriesValues(h, perCow);
    let d = "";
    let pen = false;
    vals.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
    });
    return { herd: h.herd, colour: colourFor(k), vals, d: d.trim() };
  });

  function onMove(e: React.MouseEvent<SVGRectElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / (box.width || 1)) * plotW;
    const i = Math.round((px / (plotW || 1)) * (days.length - 1));
    setHover(Math.min(days.length - 1, Math.max(0, i)));
  }

  const unit = perCow ? "kg/cow" : "kg";
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
        <svg width={width} height={HEIGHT} role="img" aria-label={`Milk yield per day (${unit}), one line per herd`} className="block">
          <Axes width={width} ticks={ticks} y={y} days={days} plotW={plotW} plotH={plotH}
            fmt={(t) => (perCow ? t.toFixed(step < 1 ? 1 : 0) : String(Math.round(t)))} />
          {hover != null && (
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--sd-muted)" strokeDasharray="3 3" />
          )}
          {lines.map((l) => (
            <path key={l.herd} d={l.d} fill="none" stroke={l.colour} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {hover != null &&
            lines.map((l) => {
              const v = l.vals[hover];
              return v != null ? (
                <circle key={l.herd} cx={x(hover)} cy={y(v)} r={4.5} fill={l.colour} stroke="var(--sd-card)" strokeWidth={2} />
              ) : null;
            })}
          <rect x={PAD.left} y={PAD.top} width={Math.max(plotW, 1)} height={plotH} fill="transparent"
            onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
        </svg>
        {hover != null && (
          <div role="tooltip"
            className="pointer-events-none absolute top-2 z-10 min-w-[11rem] rounded-md border border-[var(--sd-line)] bg-[var(--sd-card)] px-3 py-2 text-[12px] shadow-[var(--sd-shadow-2)]"
            style={{ left: Math.min(Math.max(x(hover) + 12, 0), width - 200) }}>
            <div className="mb-1 font-medium text-[var(--sd-ink)]">{shortDay(days[hover])}</div>
            {lines.map((l) => (
              <div key={l.herd} className="flex items-center justify-between gap-4 text-[var(--sd-text)]">
                <span className="flex items-center gap-1.5">
                  <span aria-hidden className="size-2 rounded-full" style={{ background: l.colour }} />
                  {l.herd}
                </span>
                <span className="tabular-nums">{l.vals[hover] == null ? "—" : `${l.vals[hover]} ${unit}`}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const QUALITY_LINES = [
  { key: "fat", label: "Butterfat %", colour: "var(--sd-data-indigo)" },
  { key: "protein", label: "Protein %", colour: "var(--sd-data-cyan)" },
  { key: "snf", label: "SNF %", colour: "var(--sd-data-purple)" },
] as const;

/** Fat / protein / SNF per batch, with a pass or fail marker under each batch. */
export function QualityChart({ tests }: { tests: QualityPoint[] }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const h = HEIGHT + 20;
  const plotW = width - PAD.left - PAD.right;
  const plotH = h - PAD.top - PAD.bottom - 20;
  const days = tests.map((t) => t.date);

  const { hi, step } = useMemo(() => {
    const vals = tests.flatMap((t) => QUALITY_LINES.map((l) => t[l.key])).filter((v): v is number => v != null);
    if (!vals.length) return { hi: 1, step: 0.25 };
    const [, b, s] = niceRange(0, Math.max(...vals));
    return { hi: b, step: s };
  }, [tests]);

  const x = (i: number) => PAD.left + (tests.length <= 1 ? plotW / 2 : (i / (tests.length - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - (v / (hi || 1)) * plotH;
  const markY = PAD.top + plotH + 14;
  const ticks: number[] = [];
  for (let v = 0; v <= hi + step / 2; v += step) ticks.push(Number(v.toFixed(6)));

  const lines = QUALITY_LINES.map((l) => {
    let d = "";
    let pen = false;
    tests.forEach((t, i) => {
      const v = t[l.key];
      if (v == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
    });
    return { ...l, d: d.trim() };
  });

  function onMove(e: React.MouseEvent<SVGRectElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / (box.width || 1)) * plotW;
    const i = Math.round((px / (plotW || 1)) * (tests.length - 1));
    setHover(Math.min(tests.length - 1, Math.max(0, i)));
  }
  const ht = hover != null ? tests[hover] : null;

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-[var(--sd-text)]" aria-label="Measures">
        {lines.map((l) => (
          <li key={l.key} className="flex items-center gap-2">
            <span aria-hidden className="h-[2px] w-4 rounded-full" style={{ background: l.colour }} />
            {l.label}
          </li>
        ))}
        <li className="flex items-center gap-2"><span aria-hidden className="size-2 rounded-full bg-[var(--sd-data-green)]" />Pass</li>
        <li className="flex items-center gap-2"><span aria-hidden className="text-[12px] font-bold leading-none text-[var(--sd-data-red)]">×</span>Fail</li>
      </ul>
      <div ref={ref} className="relative w-full">
        <svg width={width} height={h} role="img" aria-label="Milk quality per batch: butterfat, protein and SNF, with pass or fail markers" className="block">
          <Axes width={width} ticks={ticks} y={y} days={days} plotW={plotW} plotH={plotH} fmt={(t) => t.toFixed(step < 1 ? 1 : 0)} />
          {hover != null && (
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--sd-muted)" strokeDasharray="3 3" />
          )}
          {lines.map((l) => (
            <path key={l.key} d={l.d} fill="none" stroke={l.colour} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {tests.map((t, i) =>
            t.result === "Fail" ? (
              <text key={t.name} x={x(i)} y={markY} textAnchor="middle" dy="0.35em" fontSize={14} fontWeight={700} fill="var(--sd-data-red)" data-testid="mark-fail">×</text>
            ) : t.result === "Pass" ? (
              <circle key={t.name} cx={x(i)} cy={markY} r={3.5} fill="var(--sd-data-green)" data-testid="mark-pass" />
            ) : (
              <circle key={t.name} cx={x(i)} cy={markY} r={3} fill="none" stroke="var(--sd-quiet)" />
            ),
          )}
          <rect x={PAD.left} y={PAD.top} width={Math.max(plotW, 1)} height={plotH + 24} fill="transparent"
            onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
        </svg>
        {ht && (
          <div role="tooltip"
            className="pointer-events-none absolute top-2 z-10 min-w-[11rem] rounded-md border border-[var(--sd-line)] bg-[var(--sd-card)] px-3 py-2 text-[12px] shadow-[var(--sd-shadow-2)]"
            style={{ left: Math.min(Math.max(x(hover!) + 12, 0), width - 200) }}>
            <div className="mb-1 font-medium text-[var(--sd-ink)]">{shortDay(ht.date)}{ht.shift ? ` · ${ht.shift}` : ""} · {ht.result}</div>
            {QUALITY_LINES.map((l) => (
              <div key={l.key} className="flex justify-between gap-4 text-[var(--sd-text)]">
                <span>{l.label}</span>
                <span className="tabular-nums">{ht[l.key] ?? "—"}</span>
              </div>
            ))}
            {ht.ph != null && <div className="flex justify-between gap-4 text-[var(--sd-text)]"><span>pH</span><span className="tabular-nums">{ht.ph}</span></div>}
          </div>
        )}
      </div>
    </div>
  );
}

/** The milk-yield card: period selector and a per-cow toggle. */
export function YieldByHerdCard() {
  const [days, setDays] = useState(30);
  const [perCow, setPerCow] = useState(false);
  const [data, setData] = useState<MilkByHerd | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    const r = await fetchMilkByHerd(days);
    if (isError(r)) setError(r.error);
    else { setError(""); setData(r); }
    setBusy(false);
  }, [days]);
  useEffect(() => { void load(); }, [load]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Milk yield by herd</CardTitle>
        <CardDescription>Net kilograms a day, one line per herd that milked in the period.</CardDescription>
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <Periods value={days} onChange={setDays} />
          <Pill on={perCow} onClick={() => setPerCow((p) => !p)}>Per cow</Pill>
          <RefreshButton onClick={load} loading={busy} label="the yield chart" />
        </div>
      </CardHeader>
      <CardContent>
        {error ? <Notice tone="error">{error}</Notice>
          : !data ? <p className="text-[13px] text-[var(--sd-muted)]">Looking…</p>
          : data.herds.length === 0 ? <p className="text-[13px] text-[var(--sd-muted)]">No milkings recorded in the last {days} days.</p>
          : <YieldChart data={data} perCow={perCow} />}
      </CardContent>
    </Card>
  );
}

/** The quality card; the server refuses a user who may not read Milk Quality Test. */
export function QualityTrendCard() {
  const [days, setDays] = useState(30);
  const [tests, setTests] = useState<QualityPoint[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    const r = await fetchQualityTrend(days);
    if (isError(r)) setError(r.error);
    else { setError(""); setTests(r.tests); }
    setBusy(false);
  }, [days]);
  useEffect(() => { void load(); }, [load]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Milk quality</CardTitle>
        <CardDescription>Butterfat, protein and SNF for each tested batch, with its overall result beneath.</CardDescription>
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <Periods value={days} onChange={setDays} />
          <RefreshButton onClick={load} loading={busy} label="the quality chart" />
        </div>
      </CardHeader>
      <CardContent>
        {error ? <Notice tone="error">{error}</Notice>
          : !tests ? <p className="text-[13px] text-[var(--sd-muted)]">Looking…</p>
          : tests.length === 0 ? <p className="text-[13px] text-[var(--sd-muted)]">No quality tests in the last {days} days.</p>
          : <QualityChart tests={tests} />}
      </CardContent>
    </Card>
  );
}
