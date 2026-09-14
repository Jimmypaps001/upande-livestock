import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarClock, ShoppingCart } from "lucide-react";
import { DatePicker } from "@/components/DatePicker";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeaderRow,
  CardHeading,
  CardTitle,
  CardTools,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RowsSkeleton } from "@/components/Loading";
import { isError } from "@/lib/frappe";
import {
  createFeedRequest,
  getProcurement,
  type BuyLine,
  type Procurement as ProcurementData,
} from "@/lib/projection";
import { cn, fmt, todayISO } from "@/lib/utils";

const TARGETS = [14, 28, 60, 90];

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/**
 * What to buy, in one order.
 *
 * THE FARM DOES NOT BUY WHAT IT MIXES. A concentrate with a recipe of its own
 * is made here, so a shortage of it is answered by a Work Order — and what
 * actually needs buying is the raw materials it is mixed from. The list
 * therefore never offers the farm's own formulations, which is the single
 * thing this page has to get right.
 *
 * QUANTITIES ARE A SUGGESTION AND ARE EDITABLE. A store keeper who knows the
 * supplier sells in half-tonne lots, or that the maize is coming off the
 * farm's own fields next week, is right and the arithmetic is not.
 */
export function Procurement() {
  const [data, setData] = useState<ProcurementData | null>(null);
  const [target, setTarget] = useState(28);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [qty, setQty] = useState<Record<string, string>>({});
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [wanted, setWanted] = useState(addDays(todayISO(), 7));
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getProcurement(target);
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setData(r);
    setQty(Object.fromEntries(r.items.map((i) => [i.item_code, String(i.order_qty)])));
    setSkip(new Set());
  }, [target]);

  useEffect(() => {
    void load();
  }, [load]);

  const items = data?.items ?? [];
  const chosen = useMemo(
    () =>
      items
        .filter((i) => !skip.has(i.item_code))
        .map((i) => ({ item_code: i.item_code, qty: Number(qty[i.item_code] ?? i.order_qty) }))
        .filter((i) => i.qty > 0),
    [items, skip, qty],
  );

  async function raise() {
    setBusy(true);
    const r = await createFeedRequest({
      items: chosen,
      target_days: target,
      schedule_date: wanted,
    });
    setBusy(false);
    if (isError(r)) {
      setNote(r.error);
      return;
    }
    setNote(
      `${r.name} is drafted — ${r.lines} line${r.lines === 1 ? "" : "s"} into ${r.warehouse}, wanted by ${r.schedule_date}. It is not submitted; open it in the desk to send it.`,
    );
    void load();
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Feeding" title="Procurement">
        What the feed store has to buy to keep the herds fed, in one request.
        Feeds the farm mixes itself are never on this list — what those need is
        the raw materials they are made from.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}
      {note && <Notice tone="ok">{note}</Notice>}

      <FigureRow>
        <Figure loading={!data} label="Short of" value={String(items.length)} hint={`to reach ${target} days`} />
        <Figure loading={!data} label="On the order" value={String(chosen.length)} hint="lines you have kept" />
        <Figure
          loading={!data} label="Already on order"
          value={String(data?.open_requests.length ?? 0)}
          hint="last 60 days, not yet received"
        />
        <Figure loading={!data} label="Delivering to" value={data?.warehouse ? "Feed store" : "—"}
                hint={data?.warehouse ?? "no store set"} />
      </FigureRow>

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Buy up to {target} days of cover</CardTitle>
            <CardDescription>
              Quantities are what the arithmetic suggests at {data?.basis ?? "today's herds"} —
              change any of them, or drop a line the farm is covering another way.
            </CardDescription>
          </CardHeading>
          <CardTools>
            <div className="flex items-center gap-1 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] p-0.5">
              {TARGETS.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTarget(t)}
                  className={cn(
                    "rounded-[var(--sd-radius-pill)] px-2.5 py-1 text-[11.5px] font-medium transition-all",
                    t === target
                      ? "bg-[var(--sd-card)] text-[var(--sd-ink)] shadow-[var(--sd-shadow-1)]"
                      : "text-[var(--sd-muted)] hover:text-[var(--sd-ink)]",
                  )}
                >
                  {t}d
                </button>
              ))}
            </div>
            <RefreshButton onClick={load} loading={loading} label="what is short" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-4 pt-0">
          {!data ? (
            <RowsSkeleton rows={5} />
          ) : !items.length ? (
            <p className="text-[13px] text-[var(--sd-muted)]">
              Nothing is short of {target} days of cover. Nothing to buy.
            </p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-[12.5px]">
                  <thead>
                    <tr className="text-left text-[10.5px] uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
                      <th className="py-2 pr-3 font-medium">Feed</th>
                      <th className="py-2 pr-3 text-right font-medium">On hand</th>
                      <th className="py-2 pr-3 text-right font-medium">A day</th>
                      <th className="py-2 pr-3 text-right font-medium">Runs out</th>
                      <th className="py-2 pr-3 text-right font-medium">Order</th>
                      <th className="py-2 font-medium" />
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <BuyRow
                        key={item.item_code}
                        item={item}
                        value={qty[item.item_code] ?? String(item.order_qty)}
                        dropped={skip.has(item.item_code)}
                        onQty={(v) => setQty((q) => ({ ...q, [item.item_code]: v }))}
                        onToggle={() =>
                          setSkip((s) => {
                            const next = new Set(s);
                            if (next.has(item.item_code)) next.delete(item.item_code);
                            else next.add(item.item_code);
                            return next;
                          })
                        }
                      />
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-wrap items-end gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="p-wanted">Wanted by</Label>
                  <DatePicker id="p-wanted" value={wanted} min={todayISO()} onChange={setWanted} />
                </div>
                <Button onClick={raise} disabled={busy || !chosen.length}>
                  <ShoppingCart className="mr-2 h-4 w-4" strokeWidth={1.75} />
                  {busy
                    ? "Drafting…"
                    : `Draft one request for ${chosen.length} feed${chosen.length === 1 ? "" : "s"}`}
                </Button>
                <span className="text-[11.5px] text-[var(--sd-muted)]">
                  Drafted, not sent — somebody has to look at it before it reaches a supplier.
                </span>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {!!data?.open_requests.length && (
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Already on order</CardTitle>
              <CardDescription>
                Shown, not subtracted. A request raised three weeks ago and never chased is
                not stock.
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="pt-0">
            <ul className="flex flex-col gap-1">
              {data.open_requests.map((r) => (
                <li
                  key={r.name}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 px-1 py-1.5 text-[12.5px]"
                >
                  <span className="flex items-center gap-2 text-[var(--sd-ink)]">
                    <CalendarClock className="h-3.5 w-3.5 text-[var(--sd-quiet)]" strokeWidth={1.75} />
                    {r.name}
                    <span className="text-[var(--sd-muted)]">{r.status}</span>
                  </span>
                  <span className="tabular-nums text-[var(--sd-quiet)]">
                    {r.transaction_date} · {r.line_count} line{r.line_count === 1 ? "" : "s"} ·{" "}
                    {fmt(r.total_qty)}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </Page>
  );
}

function BuyRow({
  item,
  value,
  dropped,
  onQty,
  onToggle,
}: {
  item: BuyLine;
  value: string;
  dropped: boolean;
  onQty: (v: string) => void;
  onToggle: () => void;
}) {
  const urgent = item.days_cover !== null && item.days_cover < 4;
  return (
    <tr className={cn("border-t border-[var(--sd-line)]", dropped && "opacity-45")}>
      <td className="py-2.5 pr-3">
        <span className="block font-medium text-[var(--sd-ink)]">{item.item_name}</span>
        <span className="block text-[11px] text-[var(--sd-quiet)]">{item.source}</span>
      </td>
      <td className="py-2.5 pr-3 text-right tabular-nums text-[var(--sd-muted)]">
        {fmt(item.on_hand)} {item.uom}
      </td>
      <td className="py-2.5 pr-3 text-right tabular-nums text-[var(--sd-muted)]">
        {fmt(item.per_day)}
      </td>
      <td
        className={cn(
          "py-2.5 pr-3 text-right tabular-nums",
          urgent ? "text-[var(--sd-sev-critical)]" : "text-[var(--sd-muted)]",
        )}
      >
        {item.runs_out_on || "—"}
      </td>
      <td className="py-2.5 pr-3 text-right">
        <Input
          type="number"
          min={0}
          value={value}
          disabled={dropped}
          onChange={(e) => onQty(e.target.value)}
          aria-label={`Quantity of ${item.item_name} to order`}
          className="ml-auto h-8 w-28 text-right tabular-nums"
        />
      </td>
      <td className="py-2.5 text-right">
        <button
          type="button"
          onClick={onToggle}
          className="text-[11.5px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)]"
        >
          {dropped ? "Put back" : "Drop"}
        </button>
      </td>
    </tr>
  );
}
