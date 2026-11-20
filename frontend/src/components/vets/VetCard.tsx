import { Mail, Phone } from "lucide-react";
import { Card } from "@/components/ui/card";
import { VetAvatar } from "@/components/vets/VetAvatar";
import type { VetRow } from "@/lib/vets";
import { cn } from "@/lib/utils";

const dash = "—";
const n = (v: number | null | undefined, unit = "") =>
  v == null ? dash : `${Number(v).toLocaleString("en-US", { maximumFractionDigits: 1 })}${unit}`;

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 px-3 py-2.5">
      <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--sd-quiet)]">{label}</span>
      <span
        className={cn(
          "text-[22px] font-semibold leading-none tracking-[-0.02em] tabular-nums",
          value === dash ? "text-[var(--sd-quiet)]" : "text-[var(--sd-ink)]",
        )}
      >
        {value}
      </span>
      <span className="min-h-[14px] text-[10.5px] text-[var(--sd-quiet)]">{hint || ""}</span>
    </div>
  );
}

/** One vet: who they are, and the period's work in figures. */
export function VetCard({ vet }: { vet: VetRow }) {
  const k = vet.kpis;
  return (
    <Card className="flex min-w-0 flex-col gap-4 p-5" data-testid="vet-card" aria-label={vet.vet_name}>
      <div className="flex items-start gap-3">
        <VetAvatar id={vet.vet} name={vet.vet_name} image={vet.image} initials={vet.initials} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-[15px] font-semibold text-[var(--sd-ink)]">{vet.vet_name}</h3>
            <span className="rounded-full px-2 py-px text-[10.5px] font-medium text-[var(--sd-muted)] ring-1 ring-[var(--sd-line)]">
              {vet.type}
            </span>
            {!vet.enabled && (
              <span className="rounded-full px-2 py-px text-[10.5px] font-medium text-[var(--sd-data-amber)] ring-1 ring-[var(--sd-data-amber)]">
                Disabled
              </span>
            )}
            {vet.licence_expired && (
              <span
                className="rounded-full px-2 py-px text-[10.5px] font-medium text-[var(--sd-data-red)] ring-1 ring-[var(--sd-data-red)]"
                title={`Licence expired ${vet.licence_expiry}`}
              >
                Licence expired
              </span>
            )}
          </div>
          <p className="truncate text-[12px] text-[var(--sd-muted)]">
            {[vet.vet, vet.type === "External" ? vet.practice_name : "", vet.registration_number]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[12px] text-[var(--sd-muted)]">
            {vet.phone && (
              <span className="inline-flex items-center gap-1">
                <Phone className="h-3 w-3" />
                {vet.phone}
              </span>
            )}
            {vet.email && (
              <span className="inline-flex items-center gap-1">
                <Mail className="h-3 w-3" />
                {vet.email}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-y-1 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-1 py-1 shadow-[var(--sd-shadow-inset)]">
        <Kpi label="Cases opened" value={n(k.cases_opened)} hint={`${n(k.cases_open_now)} open now`} />
        <Kpi label="Cases closed" value={n(k.cases_closed)} />
        <Kpi label="Treatments" value={n(k.treatments)} />
        <Kpi label="Check-ups" value={n(k.check_ups)} />
        <Kpi label="Inseminations" value={n(k.inseminations)} />
        <Kpi label="PDs done" value={n(k.pds_done)} />
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12.5px]">
        <Row label="Pregnancy rate" value={n(k.pregnancy_rate, "%")} hint={k.inseminations ? `${k.services_confirmed} of ${k.inseminations}${k.services_pending ? `, ${k.services_pending} pending` : ""}` : undefined} />
        <Row label="Days to close" value={n(k.avg_days_to_close)} />
        <Row label="Drug cost" value={n(k.drug_cost)} />
        <Row label="Last activity" value={k.last_activity ?? dash} />
      </dl>
    </Card>
  );
}

function Row({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex min-w-0 items-baseline justify-between gap-2">
      <dt className="text-[var(--sd-muted)]">{label}</dt>
      <dd className="truncate text-right tabular-nums text-[var(--sd-ink)]" title={hint}>
        {value}
      </dd>
    </div>
  );
}
