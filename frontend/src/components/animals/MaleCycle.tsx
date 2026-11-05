import { GROWTH_ORDER, STAGES, type CycleState } from "@/lib/animals";
import { cn } from "@/lib/utils";

/**
 * A male's cycle. Not the calving loop: a steer or young bull on feed climbs a
 * LIVEWEIGHT ladder (calf, weaner, grower, finisher, market-ready), and a bull
 * kept for breeding shows whether he is at rest or in the breeding cycle.
 */
export function GrowthLadder({ cycle }: { cycle: CycleState }) {
  const g = cycle.growth;
  const stage = STAGES[cycle.stage];
  const at = GROWTH_ORDER.indexOf(cycle.stage);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[25px] font-semibold tracking-[-0.02em] text-[var(--sd-ink)]">{stage.label}</span>
        <span className="text-[12px] text-[var(--sd-muted)]">{g ? `${g.kg} kg now` : stage.note}</span>
      </div>

      {g && g.nextKg != null && (
        <div>
          <div className="mb-1 flex justify-between text-[11.5px] tabular-nums text-[var(--sd-muted)]">
            <span>{Math.round(g.fromKg)} kg</span>
            <span>
              {g.pct}% to {STAGES[g.nextStage ?? "market"].label.toLowerCase()} at {Math.round(g.nextKg)} kg
            </span>
          </div>
          <div
            className="h-2.5 overflow-hidden rounded-full bg-[var(--sd-line-soft)]"
            role="progressbar"
            aria-valuenow={g.pct}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className="h-full rounded-full" style={{ width: `${g.pct}%`, background: stage.tone }} />
          </div>
        </div>
      )}

      <ol className="flex flex-wrap gap-1.5">
        {GROWTH_ORDER.map((s, i) => (
          <li
            key={s}
            className={cn(
              "flex items-center gap-2 rounded-[var(--sd-radius-pill)] px-2.5 py-1 text-[12.5px]",
              s === cycle.stage ? "bg-[var(--sd-bg-soft)] font-semibold text-[var(--sd-ink)]" : "text-[var(--sd-muted)]",
              at >= 0 && i < at && "opacity-60",
            )}
          >
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: STAGES[s].tone, opacity: s === cycle.stage ? 1 : 0.4 }} />
            {STAGES[s].label}
          </li>
        ))}
      </ol>

      {g ? (
        <dl className="grid grid-cols-3 gap-3 text-[12.5px]">
          <Stat label="Daily gain" value={g.adg == null ? "—" : `${g.adg.toFixed(2)} kg/d`} />
          <Stat label="Days to next" value={g.daysToNext == null ? "—" : String(g.daysToNext)} />
          <Stat label="Days on feed" value={g.daysOnFeed == null ? "—" : String(g.daysOnFeed)} />
        </dl>
      ) : (
        <p className="text-[12.5px] text-[var(--sd-muted)]">{cycle.nextUp}</p>
      )}
    </div>
  );
}

export function BullStatus({ cycle }: { cycle: CycleState }) {
  const b = cycle.bull;
  const active = b?.state === "In breeding cycle";
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[25px] font-semibold tracking-[-0.02em] text-[var(--sd-ink)]">
          {cycle.class ?? "Breeding bull"}
        </span>
        {b && (
          <span
            className="rounded-[var(--sd-radius-pill)] px-3 py-1 text-[12px] font-semibold text-white"
            style={{ background: active ? "var(--sd-data-green)" : "var(--sd-quiet)" }}
          >
            {b.state}
          </span>
        )}
      </div>
      {b && (
        <p className="text-[12.5px] text-[var(--sd-muted)]">
          {b.reason}
          {b.lastService ? ` · last service ${b.lastService}` : ""}
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[10px] font-medium uppercase tracking-[0.13em] text-[var(--sd-quiet)]">{label}</dt>
      <dd className="tabular-nums text-[var(--sd-ink)]">{value}</dd>
    </div>
  );
}
