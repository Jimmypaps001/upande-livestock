import { Figure, FigureRow } from "@/components/Figure";
import { RowsSkeleton } from "@/components/Loading";
import { WeekBars } from "@/components/forecast/WeekBars";
import { adgSourceLabel, fmtKg, unforecastableNote, type OutputForecast } from "@/lib/forecast";


export function OutputTab({ data, loading }: { data: OutputForecast | null; loading: boolean }) {
  if (!data) {
    return loading ? (
      <RowsSkeleton rows={6} />
    ) : (
      <p className="px-1 py-6 text-center text-[13px] text-[var(--sd-muted)]">
        The forecast could not be loaded.
      </p>
    );
  }
  const head = data.weeks.reduce((s, w) => s + w.head, 0);
  const kg = data.weeks.reduce((s, w) => s + w.kg, 0);
  return (
    <div className="flex flex-col gap-3">
      <FigureRow>
        <Figure label="Ready in horizon" value={fmtKg(head)} unit="head" hint={`${data.horizon_weeks} weeks`} />
        <Figure label="Expected weight" value={fmtKg(Math.round(kg))} unit="kg" />
        <Figure label="Exit weight" value={fmtKg(data.exit_weight_kg)} unit="kg" />
      </FigureRow>
      {data.unforecastable > 0 && (
        <p className="px-1 text-[12.5px] text-[var(--sd-amber)]" data-testid="unforecastable">
          {unforecastableNote(data.unforecastable)}
        </p>
      )}
      <WeekBars weeks={data.weeks} />
      <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
        <table className="w-full min-w-[30rem] text-[13px]" data-testid="output-weeks">
          <thead>
            <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
              <th className="px-3 py-2.5 font-medium">Week of</th>
              <th className="px-3 py-2.5 text-right font-medium">Head</th>
              <th className="px-3 py-2.5 text-right font-medium">Kg</th>
            </tr>
          </thead>
          <tbody>
            {data.weeks.map((w) => (
              <tr key={w.week_start} className="border-b border-[var(--sd-line-soft)] last:border-0">
                <td className="px-3 py-2.5 tabular-nums">{w.week_start}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{w.head} head</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmtKg(w.kg)} kg</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
        <table className="w-full min-w-[44rem] text-[13px]" data-testid="output-bulls">
          <thead>
            <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
              <th className="px-3 py-2.5 font-medium">Tag</th>
              <th className="px-3 py-2.5 font-medium">Herd</th>
              <th className="px-3 py-2.5 text-right font-medium">Latest weight</th>
              <th className="px-3 py-2.5 text-right font-medium">Gain / day</th>
              <th className="px-3 py-2.5 font-medium">Gain from</th>
              <th className="px-3 py-2.5 text-right font-medium">Ready</th>
            </tr>
          </thead>
          <tbody>
            {data.bulls.map((b) => (
              <tr key={b.animal} className="border-b border-[var(--sd-line-soft)] last:border-0">
                <td className="px-3 py-2.5 font-medium tabular-nums text-[var(--sd-ink)]">{b.label || b.animal}</td>
                <td className="px-3 py-2.5 text-[var(--sd-muted)]">{b.herd}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {b.latest_weight_kg === null ? "—" : `${fmtKg(b.latest_weight_kg)} kg`}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {b.forecast_adg === null ? "—" : b.forecast_adg.toFixed(2)}
                </td>
                <td className="px-3 py-2.5 text-[var(--sd-muted)]">{adgSourceLabel(b.adg_source)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{b.ready_date ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
