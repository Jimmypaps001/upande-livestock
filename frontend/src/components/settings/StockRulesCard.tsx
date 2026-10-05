import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, X } from "lucide-react";
import { LinkPicker } from "@/components/settings/LinkPicker";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { isError } from "@/lib/frappe";
import {
  ruleProblem,
  sameRule,
  saveStockRules,
  stockRules,
  type StockRule,
} from "@/lib/stock-rules";

/**
 * Settings → Stock: which events post a Stock Entry, from which item groups,
 * out of which store by default, and whether the item must be named.
 *
 * One row per event type. An event can always be recorded without stock; a
 * ticked type is offered items from its groups and posts what is entered. The
 * whole list saves at once, and only the rows that changed are written.
 */
export function StockRulesCard({ canWrite }: { canWrite: boolean }) {
  const [saved, setSaved] = useState<StockRule[] | null>(null);
  const [rows, setRows] = useState<StockRule[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    const r = await stockRules();
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setSaved(r.rules);
    setRows(r.rules);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const changed = useMemo(
    () => rows.filter((row, i) => saved && !sameRule(row, saved[i])),
    [rows, saved],
  );
  const problems = changed.map(ruleProblem).filter(Boolean) as string[];

  function update(index: number, patch: Partial<StockRule>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  async function save() {
    setBusy(true);
    const r = await saveStockRules(changed);
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    setSaved(r.rules);
    setRows(r.rules);
    toast(
      r.changed.length
        ? `Saved: ${r.changed.join(", ")}.`
        : "Nothing had changed.",
      "ok",
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>What each event posts to stock</CardTitle>
        <CardDescription>
          Tick an event to offer items from its item groups and post a Stock Entry for what is
          entered. An event can still be recorded without one, unless it must name an item.
          Lines with no store come off the default store.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {failure && <p className="text-[13px] text-[var(--sd-sev-critical)]">{failure}</p>}
        {!saved && !failure && (
          <div className="flex items-center gap-2 text-[13px] text-[var(--sd-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" /> Reading the event types…
          </div>
        )}

        {saved && (
          <div className="flex flex-col divide-y divide-[var(--sd-line)]">
            {rows.map((row, i) => {
              const problem = ruleProblem(row);
              return (
                <div key={row.event_type} className="flex flex-col gap-2 py-3 lg:flex-row lg:items-start lg:gap-4">
                  <label className="flex min-w-[170px] items-center gap-2 text-[13px] font-medium text-[var(--sd-ink)]">
                    <Switch
                      checked={row.posts_stock_entry}
                      disabled={!canWrite}
                      onCheckedChange={(on) =>
                        update(i, on ? { posts_stock_entry: true } : {
                          posts_stock_entry: false, must_name_item: false,
                        })
                      }
                      aria-label={`${row.event_type} posts a stock entry`}
                    />
                    {row.event_type}
                  </label>

                  {row.posts_stock_entry ? (
                    <div className="grid flex-1 gap-2 lg:grid-cols-[2fr_1.4fr_auto]">
                      <div className="flex flex-col gap-1.5">
                        <div className="flex flex-wrap gap-1.5">
                          {row.item_groups.map((g) => (
                            <span
                              key={g}
                              className="inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] px-2.5 py-1 text-[12px] text-[var(--sd-ink)]"
                            >
                              {g}
                              {canWrite && (
                                <button
                                  type="button"
                                  aria-label={`Remove ${g}`}
                                  onClick={() => update(i, { item_groups: row.item_groups.filter((x) => x !== g) })}
                                  className="text-[var(--sd-quiet)] hover:text-[var(--sd-sev-critical)]"
                                >
                                  <X className="h-3 w-3" />
                                </button>
                              )}
                            </span>
                          ))}
                        </div>
                        {canWrite && (
                          <span className="text-[11px] uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
                            {row.item_groups.length ? "Add another item group" : "Add an item group"}
                          </span>
                        )}
                        {canWrite && (
                          <LinkPicker
                            doctype="Item Group"
                            value={null}
                            onChange={(g) => {
                              if (g && !row.item_groups.includes(g)) {
                                update(i, { item_groups: [...row.item_groups, g] });
                              }
                            }}
                          />
                        )}
                        {problem && <span className="text-[11.5px] text-[var(--sd-sev-high)]">{problem}</span>}
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="text-[11px] uppercase tracking-[0.12em] text-[var(--sd-quiet)]">Default store</span>
                        <LinkPicker
                          doctype="Warehouse"
                          value={row.default_store}
                          disabled={!canWrite}
                          onChange={(store) => update(i, { default_store: store })}
                        />
                      </div>
                      <label className="flex items-center gap-2 text-[12.5px] text-[var(--sd-muted)] lg:pt-5">
                        <Switch
                          checked={row.must_name_item}
                          disabled={!canWrite}
                          onCheckedChange={(on) => update(i, { must_name_item: on })}
                          aria-label={`${row.event_type} must name an item`}
                        />
                        Must name an item
                      </label>
                    </div>
                  ) : (
                    <span className="text-[12.5px] text-[var(--sd-quiet)] lg:pt-1">Posts no stock.</span>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {saved && canWrite && (
          <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
            <span className="mr-auto text-[12.5px] text-[var(--sd-muted)]">
              {changed.length === 0 ? "No unsaved changes" : `${changed.length} event ${changed.length === 1 ? "type" : "types"} changed`}
            </span>
            <Button variant="outline" size="sm" disabled={!changed.length || busy} onClick={() => setRows(saved)}>
              Discard
            </Button>
            <Button size="sm" disabled={!changed.length || busy || problems.length > 0} onClick={save}>
              {busy ? "Saving…" : "Save stock rules"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
