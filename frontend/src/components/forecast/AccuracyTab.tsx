import { RowsSkeleton } from "@/components/Loading";
import { fmtKg, formatErrorPct, type AccuracyRow } from "@/lib/forecast";


const dash = fmtKg;

export function AccuracyTab({ rows, loading }: { rows: AccuracyRow[] | null; loading: boolean }) {
  if (!rows) {
    return loading ? (
      <RowsSkeleton rows={6} />
    ) : (
      <p className="px-1 py-6 text-center text-[13px] text-[var(--sd-muted)]">
        The accuracy figures could not be loaded.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
      <table className="w-full min-w-[44rem] text-[13px]" data-testid="accuracy-rows">
        <thead>
          <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
            <th className="px-3 py-2.5 font-medium">Week of</th>
            <th className="px-3 py-2.5 text-right font-medium">Forecast head</th>
            <th className="px-3 py-2.5 text-right font-medium">Actual head</th>
            <th className="px-3 py-2.5 text-right font-medium">Head error</th>
            <th className="px-3 py-2.5 text-right font-medium">Forecast kg</th>
            <th className="px-3 py-2.5 text-right font-medium">Actual kg</th>
            <th className="px-3 py-2.5 text-right font-medium">Kg error</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.week_start} className="border-b border-[var(--sd-line-soft)] last:border-0">
              <td className="px-3 py-2.5 tabular-nums">{r.week_start}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{dash(r.forecast_head)}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{dash(r.actual_head)}</td>
              <td className="px-3 py-2.5 text-right font-medium tabular-nums" data-cell="error-head">
                {formatErrorPct(r.error_pct_head)}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums">{dash(r.forecast_kg)}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{dash(r.actual_kg)}</td>
              <td className="px-3 py-2.5 text-right font-medium tabular-nums" data-cell="error-kg">
                {formatErrorPct(r.error_pct_kg)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
