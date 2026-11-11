import { CalendarClock, ShieldAlert } from "lucide-react";
import { BackdatedBadge } from "@/components/BackdatedBadge";
import { DatePicker } from "@/components/DatePicker";
import { Notice } from "@/components/feeding/Notice";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import {
  addDays,
  daysBetween,
  fitsWindow,
  pdDateValid,
  type BirthCheck,
  type RetroForm,
} from "@/lib/birth-window";
import { choiceLabel, outOfStock, type StockChoice } from "@/lib/events";

function fmt(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/**
 * Why this birth cannot be recorded as it stands — and the way through.
 *
 * Shown when the dam has no confirmed pregnancy and no service whose date puts
 * this birth inside the farm's window (birth_check). The explainer says the
 * rule in the farm's own numbers; the steps below it back-record what happened
 * nine months ago: the service (and its straw), optionally the diagnosis that
 * confirmed it, and the herd she was in that day. The calves are the last step,
 * on the form underneath, and everything goes in one request.
 */
export function RetroBirth({
  dam,
  birthDate,
  check,
  form,
  onChange,
  serviceTypes,
  sires,
  straws,
  herds,
}: {
  dam: string;
  birthDate: string;
  check: BirthCheck;
  form: RetroForm;
  onChange: (next: RetroForm) => void;
  serviceTypes: string[];
  sires: string[];
  /** The Service event's items (out-of-stock ones included, marked). */
  straws: StockChoice[];
  herds: { name: string; label: string }[];
}) {
  const { min_days, max_days } = check.window;
  const set = (patch: Partial<RetroForm>) => onChange({ ...form, ...patch });
  const straw = straws.find((s) => s.value === form.straw);
  const storeChoices = straw?.locations?.length
    ? straw.locations.map((l) => ({ value: l.warehouse, label: `${l.warehouse} · ${l.qty} ${straw.uom ?? ""}`.trim() }))
    : straw?.warehouse
      ? [{ value: straw.warehouse, label: `${straw.warehouse} · none in store` }]
      : [];
  const serviceFits = !!form.service_date && fitsWindow(form.service_date, birthDate, min_days, max_days);
  const gestation = form.service_date ? daysBetween(form.service_date, birthDate) : null;
  const disabled = !check.retro_allowed;

  return (
    <div className="flex flex-col gap-4 rounded-[var(--sd-radius-lg)] border border-[var(--sd-amber-line)] bg-[var(--sd-amber-tint)] px-4 py-4" data-testid="retro-birth">
      <div className="flex items-start gap-2.5">
        <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-[var(--sd-amber)]" strokeWidth={2} />
        <div className="flex flex-col gap-1 text-[13px] text-[var(--sd-ink)]">
          <span className="font-semibold">No pregnancy on record for this birth</span>
          <span className="text-[var(--sd-text)]">
            {dam} has no confirmed pregnancy diagnosis and no service that fits a birth on {fmt(birthDate)}. A
            calf is born {min_days}–{max_days} days after its service, so she was served between{" "}
            <b>{fmt(check.service_from)}</b> and <b>{fmt(check.service_to)}</b>.
          </span>
          <span className="text-[var(--sd-muted)]">
            Back-record that service below — when it happened, how, and which herd she was in — and the birth is
            recorded with it, all at once. Everything back-recorded is marked Backdated.
          </span>
        </div>
      </div>

      {disabled && (
        <div className="flex items-start gap-2 rounded-md bg-[var(--sd-card)] px-3 py-2.5 text-[12.5px] text-[var(--sd-ink)]" role="alert">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[var(--sd-sev-critical)]" />
          <span>{check.retro_refusal || "A Livestock Manager must back-record this service."}</span>
        </div>
      )}

      <fieldset disabled={disabled} className="flex flex-col gap-4 disabled:opacity-60">
        <Step n={1} title="The service">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="r-svc-date">Service date</Label>
              <DatePicker
                id="r-svc-date"
                value={form.service_date}
                min={check.service_from}
                max={check.service_to}
                onChange={(v) => set({ service_date: v })}
                disabled={disabled}
              />
              <span className="text-[11px] text-[var(--sd-quiet)]">
                {form.service_date && !serviceFits
                  ? `Must be between ${fmt(check.service_from)} and ${fmt(check.service_to)}.`
                  : gestation !== null
                    ? `${gestation} days before the birth.`
                    : `${fmt(check.service_from)} – ${fmt(check.service_to)}`}
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="r-svc-type">How</Label>
              <Picker id="r-svc-type" value={form.service_type} onChange={(v) => set({ service_type: v })}
                      options={serviceTypes} label="Service type" disabled={disabled} />
            </div>
            {sires.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="r-svc-sire">Sire</Label>
                <Picker id="r-svc-sire" value={form.sire} onChange={(v) => set({ sire: v })} options={sires}
                        clearable clearLabel="Not known / leave blank" label="Sire" disabled={disabled} />
              </div>
            )}
          </div>
          {straws.length > 0 && !/natural/i.test(form.service_type) && (
            <div className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_6rem_minmax(0,1.4fr)]">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="r-straw">Straw used</Label>
                <Picker
                  id="r-straw"
                  value={form.straw}
                  onChange={(v) => {
                    const s = straws.find((x) => x.value === v);
                    set({ straw: v, straw_store: s?.warehouse ?? "" });
                  }}
                  options={straws.map((s) => ({ value: s.value, label: choiceLabel(s) }))}
                  clearable
                  clearLabel="No straw"
                  label="Straw used"
                  disabled={disabled}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="r-straw-qty">Straws</Label>
                <Input id="r-straw-qty" type="number" min={1} step="1" value={form.straw_qty}
                       onChange={(e) => set({ straw_qty: e.target.value })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="r-straw-store">From store</Label>
                <Picker id="r-straw-store" value={form.straw_store} onChange={(v) => set({ straw_store: v })}
                        options={storeChoices} label="From store" placeholder="—" disabled={disabled} />
              </div>
            </div>
          )}
          {straw && outOfStock(straw) && (
            <Notice tone="info">
              None of this straw is in the store. The service is still recorded; its straw issue is saved as a
              backdated draft on Transactions, to complete when the stock is in.
            </Notice>
          )}
        </Step>

        {check.allow_diagnosis && (
          <Step n={2} title="The pregnancy diagnosis (optional)">
            <label className="flex items-center gap-2 text-[12.5px] text-[var(--sd-text)]">
              <input
                type="checkbox"
                checked={form.with_diagnosis}
                onChange={(e) => set({ with_diagnosis: e.target.checked })}
              />
              She was checked and confirmed in calf
            </label>
            {form.with_diagnosis && (
              <div className="flex max-w-[16rem] flex-col gap-1.5">
                <Label htmlFor="r-pd-date">Checked on</Label>
                <DatePicker
                  id="r-pd-date"
                  value={form.diagnosis_date}
                  min={form.service_date ? addDays(form.service_date, 1) : check.service_from}
                  max={addDays(birthDate, -1)}
                  onChange={(v) => set({ diagnosis_date: v })}
                  disabled={disabled || !form.service_date}
                />
                {form.diagnosis_date && !pdDateValid(form.diagnosis_date, form.service_date, birthDate) && (
                  <span className="text-[11px] text-[var(--sd-sev-critical)]">
                    After the service and before the birth.
                  </span>
                )}
              </div>
            )}
          </Step>
        )}

        <Step n={check.allow_diagnosis ? 3 : 2} title="The herd she was in on the service date">
          <div className="flex max-w-[20rem] flex-col gap-1.5">
            <Picker id="r-herd" value={form.herd} onChange={(v) => set({ herd: v })}
                    options={herds.map((h) => ({ value: h.name, label: h.label }))}
                    label="Herd on the service date" disabled={disabled} />
            <span className="text-[11px] text-[var(--sd-quiet)]">
              {check.herd_on_service_date
                ? `Her herd history says ${check.herd_on_service_date} on that day. Change it if that is wrong — her history is corrected to match.`
                : "Recorded as a backdated move on that day; she stays where she is now."}
            </span>
          </div>
        </Step>

        <Step n={check.allow_diagnosis ? 4 : 3} title="The birth">
          <span className="text-[12.5px] text-[var(--sd-muted)]">The calves below, recorded with the rest.</span>
        </Step>
      </fieldset>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2.5">
      <div className="flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--sd-amber)] text-[11px] font-semibold text-white">
          {n}
        </span>
        <span className="text-[13px] font-semibold text-[var(--sd-ink)]">{title}</span>
        {title !== "The birth" && <BackdatedBadge />}
      </div>
      <div className="flex flex-col gap-3 pl-7">{children}</div>
    </section>
  );
}
