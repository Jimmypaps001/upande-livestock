import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Mark, Notice } from "@/components/feeding/Notice";
import { PostingDate } from "@/components/feeding/PostingDate";
import { Figure, FigureRow } from "@/components/Figure";
import { Page, PageHeading } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { isError } from "@/lib/frappe";
import { getQualityOptions, SKIPPED_NOTICE, type CaptureMode } from "@/lib/quality";
import {
  buildPayload,
  createMilkRecording,
  DISCARD_REASONS,
  emptyForm,
  formNet,
  formRevenue,
  formatTime,
  milkingOptions,
  nowHM,
  recentMilkings,
  validateForm,
  type MilkingForm,
  type MilkingHerd,
  type RecentMilking,
} from "@/lib/milking";
import { fmt, todayISO } from "@/lib/utils";

/** One labelled input, the shape the rest of this page's grid is built from. */
function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className="text-[var(--sd-muted)]">
        {label}
      </Label>
      {children}
      {hint && <span className="text-[11px] text-[var(--sd-quiet)]">{hint}</span>}
    </div>
  );
}

/**
 * Record a milking session.
 *
 * The herd picker offers only what `milking_options` answers — the lactation
 * groups it derives from Herd Movement settings — so a milking cannot be filed
 * against calves or dry cows. Everything else on the form is the Milk Recording
 * doctype's own field set, under its own names.
 *
 * Backdating works exactly as it does on Feeding: the same PostingDate control,
 * the same amber banner, the same today ceiling, and the date travels in the
 * same `recording_date` key the server's `backdate.resolve` reads. What differs
 * is downstream and worth saying on the screen: a backdated Milk Recording is
 * stamped and saved, but `on_submit` posts NO Stock Entry and no revenue
 * Journal Entry for it — that is deferred to `replay_deferred_milk`.
 */
export function Milking() {
  const [herds, setHerds] = useState<MilkingHerd[]>([]);
  const [company, setCompany] = useState<string | null>(null);
  const [operator, setOperator] = useState<string | null>(null);
  const [restricted, setRestricted] = useState<string[]>([]);
  const [loadingHerds, setLoadingHerds] = useState(true);

  const [form, setForm] = useState<MilkingForm>(emptyForm);
  const [busy, setBusy] = useState(false);
  /** Whatever the server last said. Never reworded — see components/feeding/Notice. */
  const [failure, setFailure] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lastMode, setLastMode] = useState<string | null>(null);
  // Where this farm takes its lab figures. Asked once; the form shows the
  // boxes only when the answer is "here".
  const [qualityMode, setQualityMode] = useState<CaptureMode>("At milking");

  const [backdating, setBackdating] = useState(false);
  const [postDate, setPostDate] = useState(todayISO());

  const [recent, setRecent] = useState<RecentMilking[]>([]);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [recentBusy, setRecentBusy] = useState(false);

  function set<K extends keyof MilkingForm>(key: K, value: MilkingForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  useEffect(() => {
    // Where this farm takes its lab figures. One call, on mount: the answer
    // decides whether the SCC and protein boxes belong on this form at all.
    void getQualityOptions().then((r) => {
      if (!isError(r)) setQualityMode(r.mode);
    });
  }, []);

  useEffect(() => {
    milkingOptions().then((r) => {
      setLoadingHerds(false);
      if (isError(r)) {
        setFailure(r.error);
        return;
      }
      setHerds(r.herds || []);
      setRestricted(r.restricted_to || []);
      setCompany(r.company ?? null);
      setOperator(r.employee ?? null);
    });
  }, []);

  const loadRecent = useCallback(async (herd: string) => {
    setRecentBusy(true);
    const r = await recentMilkings(herd || undefined);
    setRecentBusy(false);
    setRecent(r.rows);
    setRecentError(r.error ?? null);
  }, []);

  useEffect(() => {
    loadRecent(form.herd);
  }, [form.herd, loadRecent]);

  /** Live mode always posts today, whatever the field last held. */
  const effectiveDate = backdating ? postDate : todayISO();
  const net = formNet(form);
  const money = formRevenue(form);
  const discarded = parseFloat(form.discardedKg) > 0;
  const herdLabel =
    herds.find((h) => h.name === form.herd)?.label || form.herd || "the herd";

  async function submit() {
    const complaint = validateForm(form);
    setSuccess(null);
    if (complaint) {
      setFailure(complaint);
      return;
    }
    setFailure(null);
    setBusy(true);
    const r = await createMilkRecording(
      buildPayload(form, effectiveDate, { company, operator }),
    );
    setBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    const posted = r.stock_entry
      ? ` Stock Entry ${r.stock_entry}.`
      : " No stock was posted — a backdated recording defers its Stock Entry until it is replayed.";
    setSuccess(
      `Recorded ${r.name} — ${fmt(r.net_yield_kg)} kg net from ${herdLabel} on ${effectiveDate}.${posted}`,
    );
    setLastMode(effectiveDate !== todayISO() ? "Backdated" : null);
    // Keep the herd and the posting day; a parlour records the second milking
    // straight after the first, and retyping the herd is how the wrong one
    // gets picked.
    setForm((f) => ({
      ...emptyForm(),
      herd: f.herd,
      milkingTime: nowHM(),
      pricePerKg: f.pricePerKg,
    }));
    loadRecent(form.herd);
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Milking" title="Milking">
        Record what a herd gave at one milking. Only the herds that are in milk are
        offered — the lactation groups are read off the Herd Movement settings, so a
        renamed herd cannot quietly fall off the list.
      </PageHeading>

      <PostingDate
        backdating={backdating}
        onBackdatingChange={setBackdating}
        date={postDate}
        onDateChange={setPostDate}
        idPrefix="milk"
        dateLabel="Date milked"
        noun="recording"
      />

      {failure && <Notice tone="error">{failure}</Notice>}
      {success && (
        <Notice tone="ok">
          <div className="flex flex-wrap items-center gap-2">
            <span>{success}</span>
            {lastMode && <Mark>{lastMode}</Mark>}
          </div>
        </Notice>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Milking session</CardTitle>
          <CardDescription>
            Creates and submits a Milk Recording. A live one posts the milk into stock
            and a revenue Journal Entry; a backdated one records the yield and defers
            both until they are replayed on the day they belong to.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <Field
              id="milk-herd"
              label="Herd"
              hint={
                restricted.length
                  ? `${restricted.length} herd${restricted.length === 1 ? "" : "s"} in milk`
                  : undefined
              }
            >
              <Select value={form.herd} onValueChange={(v) => set("herd", v)}>
                <SelectTrigger id="milk-herd">
                  <SelectValue
                    placeholder={loadingHerds ? "Loading…" : "Select herd…"}
                  />
                </SelectTrigger>
                <SelectContent>
                  {herds.map((h) => (
                    <SelectItem key={h.name} value={h.name}>
                      {h.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <Field id="milk-time" label="Milking time">
              <Input
                id="milk-time"
                type="time"
                value={form.milkingTime}
                onChange={(e) => set("milkingTime", e.target.value)}
              />
            </Field>

            <Field id="milk-cows" label="Cows milked">
              <Input
                id="milk-cows"
                type="number"
                min={0}
                step={1}
                value={form.cowsMilked}
                onChange={(e) => set("cowsMilked", e.target.value)}
              />
            </Field>

            <Field id="milk-total" label="Total yield (kg)">
              <Input
                id="milk-total"
                type="number"
                min={0}
                step="any"
                value={form.totalYieldKg}
                onChange={(e) => set("totalYieldKg", e.target.value)}
              />
            </Field>

            <Field id="milk-discard" label="Discarded (kg)">
              <Input
                id="milk-discard"
                type="number"
                min={0}
                step="any"
                value={form.discardedKg}
                onChange={(e) => set("discardedKg", e.target.value)}
              />
            </Field>

            <Field
              id="milk-discard-reason"
              label="Reason for discard"
              hint={discarded ? "Required once any milk is discarded." : undefined}
            >
              <Select
                value={form.discardReason}
                onValueChange={(v) => set("discardReason", v)}
              >
                <SelectTrigger id="milk-discard-reason">
                  <SelectValue placeholder={discarded ? "Say why…" : "—"} />
                </SelectTrigger>
                <SelectContent>
                  {DISCARD_REASONS.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <Field id="milk-price" label="Price per kg">
              <Input
                id="milk-price"
                type="number"
                min={0}
                step="any"
                value={form.pricePerKg}
                onChange={(e) => set("pricePerKg", e.target.value)}
              />
            </Field>

            {/* The lab figures, only where the farm takes them. In Afterwards
                mode the server ignores these keys outright, so showing boxes
                that post nowhere would be a lie the form tells the operator. */}
            {qualityMode === "At milking" && (
              <>
                <Field id="milk-protein" label="Protein %">
                  <Input
                    id="milk-protein"
                    type="number"
                    min={0}
                    step="any"
                    value={form.proteinPercent}
                    onChange={(e) => set("proteinPercent", e.target.value)}
                  />
                </Field>

                <Field id="milk-scc" label="Bulk tank SCC">
                  <Input
                    id="milk-scc"
                    type="number"
                    min={0}
                    step="any"
                    value={form.bulkScc}
                    onChange={(e) => set("bulkScc", e.target.value)}
                  />
                </Field>
              </>
            )}

            {/* Said before the button, not after the fact: leaving these blank
                is allowed and has a consequence, and the operator should know
                what it is while they can still act on it. */}
            {qualityMode === "At milking" && !form.proteinPercent && !form.bulkScc && (
              <div className="sm:col-span-2">
                <Notice tone="info">{SKIPPED_NOTICE}</Notice>
              </div>
            )}

            {form.discardReason === "Other" && (
              <Field
                id="milk-discard-notes"
                label="Discard notes"
                hint="Required when the reason is Other."
              >
                <Input
                  id="milk-discard-notes"
                  value={form.discardNotes}
                  onChange={(e) => set("discardNotes", e.target.value)}
                />
              </Field>
            )}

            <div className="sm:col-span-2 lg:col-span-3">
              <Field id="milk-remarks" label="Remarks">
                <Input
                  id="milk-remarks"
                  value={form.remarks}
                  onChange={(e) => set("remarks", e.target.value)}
                />
              </Field>
            </div>
          </div>

          <FigureRow>
            <Figure label="Total" value={fmt(form.totalYieldKg || 0)} unit="kg" />
            <Figure label="Discarded" value={fmt(form.discardedKg || 0)} unit="kg" />
            <Figure
              label="Net to the tank"
              value={fmt(net)}
              unit="kg"
              hint={net < 0 ? "More discarded than milked." : undefined}
            />
            <Figure label="Estimated revenue" value={fmt(money)} unit="KES" />
          </FigureRow>

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={submit} disabled={busy}>
              {busy ? "Recording…" : "Record & submit"}
            </Button>
            {effectiveDate !== todayISO() && <Mark>Backdated · {effectiveDate}</Mark>}
            <span className="text-[12px] text-[var(--sd-quiet)]">
              {effectiveDate !== todayISO()
                ? "This recording will be stamped backdated and will not post milk into stock."
                : "This posts the milk into stock and a revenue journal entry."}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Recent recordings
            {recentBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          </CardTitle>
          <CardDescription>
            {form.herd
              ? `The last few for ${herdLabel} — check one of these is not the milking you are about to type.`
              : "The last few across every herd. Pick a herd above to narrow it."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {recentError ? (
            <Notice tone="error">{recentError}</Notice>
          ) : recent.length === 0 ? (
            <p className="text-[13px] text-[var(--sd-muted)]">
              {recentBusy ? "Looking…" : "Nothing recorded yet."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Time</TableHead>
                    <TableHead>Herd</TableHead>
                    <TableHead className="text-right">Cows</TableHead>
                    <TableHead className="text-right">Total kg</TableHead>
                    <TableHead className="text-right">Discarded kg</TableHead>
                    <TableHead className="text-right">Net kg</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recent.map((r) => (
                    <TableRow key={r.name}>
                      <TableCell className="whitespace-nowrap">
                        <span className="flex items-center gap-2">
                          {r.recording_date}
                          {r.custom_is_backdated ? <Mark>Backdated</Mark> : null}
                        </span>
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {formatTime(r.milking_time)}
                      </TableCell>
                      <TableCell>{r.herd}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {r.cows_milked || 0}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmt(r.total_yield_kg)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmt(r.discarded_kg)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmt(r.net_yield_kg)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
