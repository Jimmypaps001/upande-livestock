import { useState } from "react";
import { Factory, Loader2 } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/Toast";
import { isError } from "@/lib/frappe";
import { manufactureAllFeeds, type AllFeeds } from "@/lib/nutrition";
import { fmt, num, todayISO } from "@/lib/utils";

/**
 * Manufacture all: the day's feed for every herd still owed some, in one go.
 *
 * It lives on the Feeding page because it IS feeding — it moves stock — and
 * the Ration Editor only writes recipes. The server decides everything
 * (`manufacture_all_feeds`): which herds are still owed feed, what the stores
 * can cover, and which concentrates have to be mixed first. The button opens
 * a preview; nothing posts until "Mix them all".
 *
 * On a farm that does not feed by head count, the preview offers head count x
 * per head as a suggestion and mixes the totals the operator types; a herd
 * left blank is not fed.
 */
export function ManufactureAll({ onDone }: { onDone?: () => void }) {
  const [all, setAll] = useState<AllFeeds | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<AllFeeds | null>(null);
  // The group totals typed on a farm that does not feed by head count.
  const [totals, setTotals] = useState<Record<string, string>>({});
  const toast = useToast();

  async function openPreview() {
    setDone(null);
    setAll(null);
    setOpen(true);
    const r = await manufactureAllFeeds({ date: todayISO(), preview: true });
    if (isError(r)) {
      setOpen(false);
      toast(r.error, "error");
      return;
    }
    setAll(r);
    setTotals(Object.fromEntries(r.herds.map((h) => [h.herd, String(h.suggested_qty ?? h.qty)])));
  }

  // Off, the operator's totals are what is mixed; a herd left blank is not fed.
  const typingTotals = all?.feed_by_head_count === false;

  async function confirm() {
    setBusy(true);
    const typed = typingTotals
      ? Object.fromEntries(
          Object.entries(totals)
            .map(([h, v]) => [h, num(v)] as const)
            .filter(([, v]) => v > 0),
        )
      : undefined;
    const r = await manufactureAllFeeds({ date: todayISO(), totals: typed });
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    setDone(r);
    onDone?.();
  }

  return (
    <>
      <Button onClick={() => void openPreview()}>
        <Factory className="mr-2 h-4 w-4" strokeWidth={1.75} />
        Manufacture all
      </Button>

      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Manufacture all</DialogTitle>
            <DialogDescription>
              Mix the day&rsquo;s feed for every herd that is still owed some. The stores decide
              what can be covered; anything short is recorded and waits for stock.
            </DialogDescription>
          </DialogHeader>

          {!all && <Loader2 className="h-4 w-4 animate-spin" />}
          {all && !done && (
            <div className="flex flex-col gap-3">
              {all.concentrates.length > 0 && (
                <div>
                  <p className="text-[12.5px] font-medium">Concentrates mixed first</p>
                  <ul className="text-[13px] text-[var(--sd-muted)]">
                    {all.concentrates.map((c) => (
                      <li key={c.item_code}>
                        {c.item_name}: {fmt(c.qty)} kg
                        {c.batches ? ` (${c.batches} batch${c.batches === 1 ? "" : "es"})` : ""}
                        {c.can_manufacture === false ? " — short of ingredients" : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {all.herds.length === 0 ? (
                <p className="text-[13px] text-[var(--sd-muted)]">Every herd is already fed for today.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-separate border-spacing-0 text-[13px]">
                    <thead>
                      <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--sd-quiet)]">
                        <th className="py-1 pr-4 font-medium">Herd</th>
                        <th className="py-1 pr-4 text-right font-medium">Head</th>
                        <th className="py-1 pr-4 text-right font-medium">Portion</th>
                        <th className="py-1 pr-4 text-right font-medium">
                          {typingTotals ? "Suggested (kg)" : "Mix (kg)"}
                        </th>
                        {typingTotals && <th className="py-1 pr-4 text-right font-medium">Total fed (kg)</th>}
                        <th className="py-1 pl-4 text-left font-medium">Stock</th>
                      </tr>
                    </thead>
                    <tbody>
                      {all.herds.map((h) => (
                        <tr key={h.herd} className="border-t border-[var(--sd-line)]">
                          <td className="py-1.5 pr-4 align-top">{h.herd}</td>
                          <td className="py-1.5 pr-4 text-right align-top tabular-nums">{h.heads}</td>
                          <td className="py-1.5 pr-4 text-right align-top tabular-nums">{fmt(h.portion)}</td>
                          <td className="py-1.5 pr-4 text-right align-top tabular-nums">
                            {fmt(typingTotals ? (h.suggested_qty ?? h.qty) : h.qty)}
                          </td>
                          {typingTotals && (
                            <td className="py-1 pr-4 text-right align-top">
                              <Input
                                aria-label={`Total fed to ${h.herd} (kg)`}
                                type="number"
                                min={0}
                                step="any"
                                className="ml-auto h-8 w-24 text-right tabular-nums"
                                value={totals[h.herd] ?? ""}
                                onChange={(e) => setTotals((s) => ({ ...s, [h.herd]: e.target.value }))}
                              />
                            </td>
                          )}
                          <td className="max-w-[220px] py-1.5 pl-4 align-top text-[12px] break-words">
                            {h.short?.length ? (
                              <span className="text-[var(--sd-sev-critical)]">
                                short: {h.short.map((s) => s.item_name).join(", ")}
                              </span>
                            ) : (
                              "covered"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {typingTotals && (
                <p className="text-[12px] text-[var(--sd-muted)]">
                  This farm does not feed by head count: the suggestion is head count &times; ration
                  per head ({fmt(all.herds.reduce((s, h) => s + (h.suggested_qty ?? h.qty), 0))} kg in
                  all). What you type is what is mixed; a herd left blank is not fed.
                </p>
              )}
              {all.skipped.length > 0 && (
                <p className="text-[12px] text-[var(--sd-muted)]">
                  Left out: {all.skipped.map((s) => `${s.herd} (${s.reason})`).join(", ")}.
                </p>
              )}
              <div className="flex gap-3">
                <Button onClick={() => void confirm()} disabled={busy || all.herds.length === 0}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Mix them all"}
                </Button>
                <Button variant="secondary" onClick={() => setOpen(false)} disabled={busy}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
          {done && (
            <div className="flex flex-col gap-2">
              {done.concentrates.map((c) => (
                <Notice key={c.item_code} tone={c.warning ? "error" : "ok"}>
                  {c.item_name}: {c.warning ? c.warning : `mixed ${fmt(c.qty)} kg — ${c.work_order}`}
                </Notice>
              ))}
              {done.herds.map((h) => (
                <Notice key={h.herd} tone={h.status === "error" ? "error" : h.warnings?.length ? "info" : "ok"}>
                  {h.herd}:{" "}
                  {h.status === "error"
                    ? h.error
                    : `${h.status} — ${fmt(h.produced_qty ?? h.qty)} kg, ${h.work_order ?? ""}${
                        h.warnings?.length ? ` · ${h.warnings.join("; ")}` : ""
                      }`}
                </Notice>
              ))}
              <div>
                <Button onClick={() => setOpen(false)}>Close</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
