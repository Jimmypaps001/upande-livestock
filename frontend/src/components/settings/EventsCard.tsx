import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, X } from "lucide-react";
import { LinkPicker } from "@/components/settings/LinkPicker";
import { SettingField } from "@/components/settings/SettingField";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { isError } from "@/lib/frappe";
import {
  changePayload,
  pendingChanges,
  saveLivestockSettings,
  type SettingsField,
  type SettingsValue,
} from "@/lib/settings";
import {
  detailsShown,
  ruleProblem,
  ruleSummary,
  sameRule,
  saveStockRules,
  stockRules,
  type StockRule,
} from "@/lib/stock-rules";

/**
 * Settings → Events: which events this farm records, and for each one it does,
 * what it uses from stock and how often it comes round.
 *
 * One row per event type, led by its Enabled switch. Some farms do not do a
 * pregnancy diagnosis; switched off, an event leaves the menus (web and phone),
 * its alerts and due lists stop and the server refuses a new one. Its details
 * are shown and editable only while it is on — off, the row folds to one line
 * and keeps the details as they were, so switching it back on restores them.
 *
 * "Uses stock" is the event type's own rule (item groups, default store, must
 * name an item). "How often" is the Livestock Settings timings that govern the
 * event — the same fields the guards and alerts read, shown here beside the
 * event they belong to rather than copied. One Save writes both.
 */
export function EventsCard({
  canWrite,
  fields,
  values,
  onSettingsSaved,
}: {
  canWrite: boolean;
  /** Every Livestock Settings field, for the timings' labels, help and controls. */
  fields: SettingsField[];
  values: Record<string, SettingsValue>;
  /** The settings as stored after a timing save, so the rest of the page redraws from them. */
  onSettingsSaved: (values: Record<string, SettingsValue>) => void;
}) {
  const [saved, setSaved] = useState<StockRule[] | null>(null);
  const [rows, setRows] = useState<StockRule[]>([]);
  const [timingDraft, setTimingDraft] = useState<Record<string, SettingsValue>>({});
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

  const byName = useMemo(() => new Map(fields.map((f) => [f.fieldname, f])), [fields]);
  const changed = useMemo(
    () => rows.filter((row, i) => saved && !sameRule(row, saved[i])),
    [rows, saved],
  );
  // Only the timings of events that are on: a folded event's fields are not on screen.
  const timingChanges = useMemo(() => {
    const shown = new Set(rows.filter(detailsShown).flatMap((r) => r.timings));
    const draft = Object.fromEntries(Object.entries(timingDraft).filter(([f]) => shown.has(f)));
    return pendingChanges(fields, values, draft);
  }, [rows, timingDraft, fields, values]);
  const problems = changed.map(ruleProblem).filter(Boolean) as string[];
  const pending = changed.length + timingChanges.length;

  function update(index: number, patch: Partial<StockRule>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  async function save() {
    setBusy(true);
    const said: string[] = [];
    if (changed.length) {
      const r = await saveStockRules(changed);
      if (isError(r)) {
        setBusy(false);
        toast(r.error, "error");
        return;
      }
      setSaved(r.rules);
      setRows(r.rules);
      said.push(...r.changed);
    }
    if (timingChanges.length) {
      const r = await saveLivestockSettings(changePayload(timingChanges));
      if (isError(r)) {
        setBusy(false);
        // The server's words: it names the field and says why (a 0, a blank).
        toast(r.error, "error");
        return;
      }
      setTimingDraft({});
      onSettingsSaved(r.values);
      said.push(...Object.keys(r.changed || {}).map((f) => byName.get(f)?.label || f));
    }
    setBusy(false);
    toast(said.length ? `Saved: ${said.join(", ")}.` : "Nothing had changed.", "ok");
  }

  function discard() {
    if (saved) setRows(saved);
    setTimingDraft({});
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Events this farm records</CardTitle>
        <CardDescription>
          Switch off an event the farm does not do — a pregnancy diagnosis, say. It leaves the
          menus on the web and the phone, its alerts and due lists stop, and it cannot be
          recorded. Records already made stay. While an event is on, set whether it uses stock
          and how often it comes round.
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
              const open = detailsShown(row);
              const timingFields = row.timings
                .map((f) => byName.get(f))
                .filter((f): f is SettingsField => !!f);
              return (
                <section
                  key={row.event_type}
                  aria-label={row.event_type}
                  data-enabled={open ? "true" : "false"}
                  className="flex flex-col gap-3 py-3"
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <label className="flex min-w-[200px] items-center gap-2 text-[13.5px] font-semibold text-[var(--sd-ink)]">
                      <Switch
                        checked={row.enabled}
                        disabled={!canWrite}
                        onCheckedChange={(on) => update(i, { enabled: on })}
                        aria-label={`${row.event_type} enabled`}
                      />
                      <span className={open ? "" : "text-[var(--sd-quiet)]"}>{row.event_type}</span>
                    </label>
                    <span className="text-[12.5px] text-[var(--sd-quiet)]">{ruleSummary(row)}</span>
                  </div>

                  {open && (
                    <div className="grid gap-4 pl-1 lg:grid-cols-2 lg:pl-11">
                      <div className="flex flex-col gap-2">
                        <span className="text-[11px] uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
                          Uses stock
                        </span>
                        <label className="flex items-center gap-2 text-[12.5px] text-[var(--sd-muted)]">
                          <Switch
                            checked={row.posts_stock_entry}
                            disabled={!canWrite}
                            onCheckedChange={(on) =>
                              update(i, on ? { posts_stock_entry: true } : {
                                posts_stock_entry: false, must_name_item: false,
                              })
                            }
                            aria-label={`${row.event_type} uses stock`}
                          />
                          {row.posts_stock_entry ? "Yes — offers items and posts a Stock Entry" : "No"}
                        </label>

                        {row.posts_stock_entry && (
                          <div className="flex flex-col gap-2">
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
                              <>
                                <span className="text-[11px] text-[var(--sd-quiet)]">
                                  {row.item_groups.length ? "Add another item group" : "Add the item group it draws from"}
                                </span>
                                <LinkPicker
                                  doctype="Item Group"
                                  value={null}
                                  onChange={(g) => {
                                    if (g && !row.item_groups.includes(g)) {
                                      update(i, { item_groups: [...row.item_groups, g] });
                                    }
                                  }}
                                />
                              </>
                            )}
                            {problem && <span className="text-[11.5px] text-[var(--sd-sev-high)]">{problem}</span>}
                            <span className="text-[11px] text-[var(--sd-quiet)]">Default store</span>
                            <LinkPicker
                              doctype="Warehouse"
                              value={row.default_store}
                              disabled={!canWrite}
                              onChange={(store) => update(i, { default_store: store })}
                            />
                            <label className="flex items-center gap-2 text-[12.5px] text-[var(--sd-muted)]">
                              <Switch
                                checked={row.must_name_item}
                                disabled={!canWrite}
                                onCheckedChange={(on) => update(i, { must_name_item: on })}
                                aria-label={`${row.event_type} must name an item`}
                              />
                              Must name an item
                            </label>
                          </div>
                        )}
                      </div>

                      <div className="flex flex-col gap-2">
                        <span className="text-[11px] uppercase tracking-[0.12em] text-[var(--sd-quiet)]">
                          How often
                        </span>
                        {timingFields.length ? (
                          <div className="grid gap-3 sm:grid-cols-2">
                            {timingFields.map((field) => (
                              <SettingField
                                key={field.fieldname}
                                field={field}
                                stored={values[field.fieldname] ?? null}
                                value={
                                  field.fieldname in timingDraft
                                    ? timingDraft[field.fieldname]
                                    : (values[field.fieldname] ?? null)
                                }
                                onChange={(next) =>
                                  setTimingDraft((d) => ({ ...d, [field.fieldname]: next }))
                                }
                                disabled={!canWrite}
                              />
                            ))}
                          </div>
                        ) : (
                          <span className="text-[12.5px] text-[var(--sd-quiet)]">
                            Recorded when it happens; no due rule.
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        )}

        {saved && canWrite && (
          <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
            <span className="mr-auto text-[12.5px] text-[var(--sd-muted)]">
              {pending === 0 ? "No unsaved changes" : `${pending} unsaved ${pending === 1 ? "change" : "changes"}`}
            </span>
            <Button variant="outline" size="sm" disabled={!pending || busy} onClick={discard}>
              Discard
            </Button>
            <Button size="sm" disabled={!pending || busy || problems.length > 0} onClick={save}>
              {busy ? "Saving…" : "Save events"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
