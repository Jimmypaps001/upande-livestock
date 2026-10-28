import { useState } from "react";
import { Notice, Pill } from "@/components/feeding/Notice";
import { RowsSkeleton } from "@/components/Loading";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  STATUS_TONE,
  fmtKg,
  mondayOf,
  saveBuyerCommitment,
  type CoverRow,
} from "@/lib/forecast";
import { isError } from "@/lib/frappe";


export function CoverTab({
  rows,
  loading,
  onSaved,
}: {
  rows: CoverRow[] | null;
  loading: boolean;
  onSaved: () => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      {!rows ? (
        loading ? (
          <RowsSkeleton rows={6} />
        ) : (
          <p className="px-1 py-6 text-center text-[13px] text-[var(--sd-muted)]">
            The cover could not be loaded.
          </p>
        )
      ) : (
        <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
          <table className="w-full min-w-[44rem] text-[13px]" data-testid="cover-rows">
            <thead>
              <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
                <th className="px-3 py-2.5 font-medium">Week of</th>
                <th className="px-3 py-2.5 text-right font-medium">Ready</th>
                <th className="px-3 py-2.5 text-right font-medium">Carried in</th>
                <th className="px-3 py-2.5 text-right font-medium">Committed</th>
                <th className="px-3 py-2.5 text-right font-medium">Balance</th>
                <th className="px-3 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.week_start} className="border-b border-[var(--sd-line-soft)] last:border-0">
                  <td className="px-3 py-2.5 tabular-nums">{r.week_start}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{r.ready_head} head</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--sd-muted)]">
                    {r.carry_in_head} head
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {r.committed_head} head
                    {r.committed_kg ? (
                      <div className="text-[11px] text-[var(--sd-quiet)]">{fmtKg(r.committed_kg)} kg</div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 text-right font-medium tabular-nums">{r.balance_head}</td>
                  <td className="px-3 py-2.5">
                    <span data-status={r.status}>
                      {r.status === "Idle" ? (
                        <span className="text-[12px] text-[var(--sd-quiet)]">Idle</span>
                      ) : (
                        <Pill tone={STATUS_TONE[r.status] ?? "mute"}>{r.status}</Pill>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <CommitmentForm onSaved={onSaved} />
    </div>
  );
}

function CommitmentForm({ onSaved }: { onSaved: () => void }) {
  const [customer, setCustomer] = useState("");
  const [week, setWeek] = useState("");
  const [head, setHead] = useState("");
  const [minKg, setMinKg] = useState("");
  const [price, setPrice] = useState("");
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const toast = useToast();

  async function save() {
    setSaving(true);
    setFailure(null);
    const r = await saveBuyerCommitment({
      customer: customer.trim(),
      week_start: mondayOf(week),
      head: Number(head),
      ...(minKg ? { min_weight_kg: Number(minKg) } : {}),
      ...(price ? { price_per_kg: Number(price) } : {}),
    });
    setSaving(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    toast("Commitment saved.");
    setCustomer("");
    setWeek("");
    setHead("");
    setMinKg("");
    setPrice("");
    onSaved();
  }

  const ready = customer.trim() !== "" && /^\d{4}-\d{2}-\d{2}$/.test(week) && Number(head) > 0;
  return (
    <form
      className="grid gap-3 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] p-4 sm:grid-cols-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready && !saving) void save();
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="lbc-customer">Customer</Label>
        <Input id="lbc-customer" value={customer} onChange={(e) => setCustomer(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="lbc-week">Week (any day)</Label>
        <Input id="lbc-week" type="date" value={week} onChange={(e) => setWeek(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="lbc-head">Head</Label>
        <Input id="lbc-head" type="number" min={1} value={head} onChange={(e) => setHead(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="lbc-min">Minimum weight (kg)</Label>
        <Input id="lbc-min" type="number" min={0} value={minKg} onChange={(e) => setMinKg(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="lbc-price">Price per kg</Label>
        <Input id="lbc-price" type="number" min={0} value={price} onChange={(e) => setPrice(e.target.value)} />
      </div>
      <div className="flex items-center gap-3 sm:col-span-5">
        <Button type="submit" className="rounded-full" disabled={!ready || saving}>
          {saving ? "Saving…" : "Add commitment"}
        </Button>
        {week && /^\d{4}-\d{2}-\d{2}$/.test(week) && (
          <span className="text-[12px] text-[var(--sd-muted)]">Week of {mondayOf(week)}</span>
        )}
      </div>
      {failure && (
        <div className="sm:col-span-5">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
    </form>
  );
}
