import { useCallback, useEffect, useState } from "react";
import { Loader2, Undo2, X } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { useToast } from "@/components/Toast";
import { DatePicker } from "@/components/DatePicker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { isError } from "@/lib/frappe";
import { canMix } from "@/lib/roles";
import {
  APPETITE_LABEL,
  amendFeedDay,
  animalIntake,
  feedDayProgram,
  kgText,
  manufactureFeedActuals,
  pctText,
  resetFeedDay,
  type AnimalIntake,
  type HerdDay,
} from "@/lib/feed-actuals";
import { fmt, num, todayISO } from "@/lib/utils";

/** One component line: the plan beside what was fed, per herd and per animal. */
function Lines({ day }: { day: HerdDay }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--sd-quiet)]">
            <th className="py-1.5 pr-3 font-medium">Component</th>
            <th className="py-1.5 pr-3 text-right font-medium">Planned</th>
            <th className="py-1.5 pr-3 text-right font-medium">Fed</th>
            <th className="py-1.5 pr-3 text-right font-medium">Planned per animal</th>
            <th className="py-1.5 text-right font-medium">Fed per animal</th>
          </tr>
        </thead>
        <tbody>
          {day.components.map((c) => {
            const changed = Math.abs(c.actual_kg - c.planned_kg) > 1e-6;
            return (
              <tr
                key={c.item_code}
                className={`border-t border-[var(--sd-line)] ${c.removed ? "text-[var(--sd-quiet)] line-through" : ""}`}
              >
                <td className="py-1.5 pr-3">{c.item_name}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  {fmt(c.planned_kg)} {c.uom}
                </td>
                <td className={`py-1.5 pr-3 text-right tabular-nums ${changed ? "font-semibold" : ""}`}>
                  {fmt(c.actual_kg)} {c.uom}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{fmt(c.planned_per_head)}</td>
                <td className="py-1.5 text-right tabular-nums">{fmt(c.actual_per_head)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Amend: change the kilograms of any component actually fed. The recipe is not touched. */
function AmendDialog({
  day,
  onClose,
  onSaved,
}: {
  day: HerdDay;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(day.components.map((c) => [c.item_code, kgText(c.actual_kg)])),
  );
  // Items struck off: not used at all that day. Saved as 0 and left out of the mix.
  const [removed, setRemoved] = useState<Set<string>>(
    () => new Set(day.components.filter((c) => c.removed).map((c) => c.item_code)),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  function setGone(code: string, gone: boolean) {
    setRemoved((prev) => {
      const next = new Set(prev);
      if (gone) next.add(code);
      else next.delete(code);
      return next;
    });
  }

  async function save() {
    setBusy(true);
    setError(null);
    const r = await amendFeedDay(
      day.herd,
      day.date,
      day.components.map((c) => ({
        item_code: c.item_code,
        actual_kg: removed.has(c.item_code) ? 0 : num(values[c.item_code]),
      })),
    );
    setBusy(false);
    if (isError(r)) {
      setError(r.error);
      return;
    }
    toast(`Saved what ${day.herd_name} was fed. The recipe is unchanged.`, "ok");
    onSaved();
    onClose();
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Amend {day.herd_name}</DialogTitle>
          <DialogDescription>
            Change the kilograms of any component actually fed on {day.date}. The herd&rsquo;s
            recipe stays as it is and so does every other day; this day&rsquo;s feed is mixed from what
            you enter here. Use the X on an item that was not used at all.
          </DialogDescription>
        </DialogHeader>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="flex max-h-[60vh] flex-col gap-2 overflow-y-auto">
          {day.components.map((c) => {
            const gone = removed.has(c.item_code);
            return (
              <div key={c.item_code} className="grid grid-cols-[1fr_7rem_2rem] items-center gap-2 text-[13px]">
                <label
                  htmlFor={`amend-${c.item_code}`}
                  className={gone ? "text-[var(--sd-quiet)] line-through" : ""}
                >
                  {c.item_name}
                  <span className="block text-[11px] text-[var(--sd-quiet)]">
                    {gone ? "Not used today, left out of the mix" : `Planned ${fmt(c.planned_kg)} ${c.uom}`}
                  </span>
                </label>
                <Input
                  id={`amend-${c.item_code}`}
                  inputMode="decimal"
                  disabled={gone}
                  value={gone ? "0" : (values[c.item_code] ?? "")}
                  onChange={(e) => setValues((v) => ({ ...v, [c.item_code]: e.target.value }))}
                  className={`text-right tabular-nums ${gone ? "line-through" : ""}`}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  className="h-8 w-8 p-0"
                  aria-label={gone ? `Put ${c.item_name} back` : `Remove ${c.item_name}, not used today`}
                  title={gone ? "Undo" : "Not used today"}
                  onClick={() => setGone(c.item_code, !gone)}
                >
                  {gone ? <Undo2 className="h-4 w-4" /> : <X className="h-4 w-4" />}
                </Button>
              </div>
            );
          })}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={save} disabled={busy}>
            {busy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            Save what was fed
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function HerdDayCard({
  day,
  onChanged,
  employee,
  blocked,
}: {
  day: HerdDay;
  onChanged: () => void;
  employee?: string;
  /** Why nothing can be changed (view-only user), or null. */
  blocked?: string | null;
}) {
  const [amending, setAmending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [intake, setIntake] = useState<AnimalIntake | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const toast = useToast();
  const mixed = day.status === "Manufactured" || day.status === "Waiting for stock";

  async function mix() {
    setBusy(true);
    setMessage(null);
    const r = await manufactureFeedActuals(day.herd, day.date, employee);
    setBusy(false);
    if (isError(r)) {
      setMessage(r.error);
      return;
    }
    toast(
      r.pending
        ? `Recorded what ${day.herd_name} was fed. The stock is short, so it waits as a draft dated ${day.date}.`
        : `Mixed and issued what ${day.herd_name} was fed.`,
      "ok",
    );
    onChanged();
  }

  async function reset() {
    setBusy(true);
    setMessage(null);
    const r = await resetFeedDay(day.herd, day.date);
    setBusy(false);
    if (isError(r)) {
      setMessage(r.error);
      return;
    }
    toast(`${day.herd_name} is back to the recipe for ${day.date}.`, "ok");
    onChanged();
  }

  async function showAnimals() {
    if (intake) {
      setIntake(null);
      return;
    }
    const r = await animalIntake(day.herd, day.date);
    if (isError(r)) setMessage(r.error);
    else setIntake(r);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {day.herd_name}
          <span className="rounded-full bg-[var(--sd-line)] px-2 py-0.5 text-[11px] font-medium">
            {day.status}
          </span>
        </CardTitle>
        <CardDescription>
          {day.head_count} head. Planned {fmt(day.planned_kg)} kg, fed {fmt(day.actual_kg)} kg
          {day.amended ? ` (${day.variance_kg > 0 ? "+" : ""}${fmt(day.variance_kg)} kg)` : ""}.
          Per animal: planned {fmt(day.planned_per_head)} kg, fed {fmt(day.actual_per_head)} kg.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {message && <Notice tone="error">{message}</Notice>}
        {blocked && <Notice tone="info">{blocked}</Notice>}
        {day.draft_entries.length > 0 && (
          <Notice tone="info">
            Waiting for stock: {day.draft_entries.join(", ")} stays a draft dated {day.date} until
            the feed is in. Post it from Transactions.
          </Notice>
        )}
        <Lines day={day} />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={mixed || !!blocked} onClick={() => setAmending(true)}>
            Amend
          </Button>
          {day.record && !mixed && (
            <Button variant="outline" disabled={busy || !!blocked} onClick={reset}>
              Reset to recipe
            </Button>
          )}
          {canMix() && (
            <Button disabled={mixed || busy || !!blocked} onClick={mix}>
              {busy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Mix and issue what was fed
            </Button>
          )}
          <Button variant="ghost" onClick={showAnimals}>
            {intake ? "Hide animals" : "Per animal"}
          </Button>
        </div>
        {intake && (
          <div className="max-h-64 overflow-auto text-[13px]">
            <table className="w-full">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--sd-quiet)]">
                  <th className="py-1 pr-3 font-medium">Animal</th>
                  <th className="py-1 pr-3 text-right font-medium">Planned kg</th>
                  <th className="py-1 pr-3 text-right font-medium">Fed kg</th>
                  <th className="py-1 pr-3 text-right font-medium">Difference</th>
                  <th className="py-1 text-right font-medium">Appetite</th>
                </tr>
              </thead>
              <tbody>
                {intake.animals.map((a) => (
                  <tr key={a.animal} className="border-t border-[var(--sd-line)]">
                    <td className="py-1 pr-3">{a.tag}</td>
                    <td className="py-1 pr-3 text-right tabular-nums">{fmt(a.planned_kg)}</td>
                    <td className="py-1 pr-3 text-right tabular-nums">{fmt(a.actual_kg)}</td>
                    <td className="py-1 pr-3 text-right tabular-nums">{pctText(a.variance_pct)}</td>
                    <td className="py-1 text-right">{APPETITE_LABEL[a.appetite]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
      {amending && <AmendDialog day={day} onClose={() => setAmending(false)} onSaved={onChanged} />}
    </Card>
  );
}

/**
 * The day sheet: every herd's formula for a day. Each component shows its
 * planned kg for the herd and per animal beside what was actually fed, and
 * Amend changes the actuals without touching the herd's recipe. What is fed is
 * what gets mixed and issued; with short stock the mix waits as a draft.
 */
export function FeedDay({
  employee,
  blocked,
}: {
  /** The operator chosen at the top of the Feeding page. */
  employee?: string;
  /** The view-only sentence, when this user cannot record at all. */
  blocked?: string | null;
}) {
  const [date, setDate] = useState(todayISO());
  const [days, setDays] = useState<HerdDay[] | null>(null);
  const [setup, setSetup] = useState<string[]>([]);
  const [failure, setFailure] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await feedDayProgram(date);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setDays(r.herds);
    setSetup(r.setup);
  }, [date]);

  useEffect(() => {
    setDays(null);
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex w-full max-w-xs flex-col gap-1.5">
        <span className="text-[13px] text-[var(--sd-muted)]">Day</span>
        <DatePicker value={date} onChange={setDate} max={todayISO()} aria-label="Day" />
      </div>
      {setup.map((s) => (
        <Notice key={s} tone="info">
          {s}
        </Notice>
      ))}
      {failure && <Notice tone="error">{failure}</Notice>}
      {!days && !failure && (
        <div className="flex items-center gap-2 text-[13px] text-[var(--sd-muted)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading the day&rsquo;s feed…
        </div>
      )}
      {days?.length === 0 && <Notice tone="info">No herd has a ration to feed.</Notice>}
      {days?.map((d) => (
        <HerdDayCard
          key={`${d.herd}-${d.date}-${d.status}-${d.actual_kg}`}
          day={d}
          onChanged={load}
          employee={employee}
          blocked={blocked}
        />
      ))}
    </div>
  );
}
