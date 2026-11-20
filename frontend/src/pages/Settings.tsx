import { useCallback, useEffect, useMemo, useState } from "react";
import { can } from "@/lib/can";
import { Loader2, ShieldAlert } from "lucide-react";
import { AppreciationRun } from "@/components/settings/AppreciationRun";
import { BackdatingSetting } from "@/components/settings/BackdatingSetting";
import { ChildTableEditor, tableDirty } from "@/components/settings/ChildTableEditor";
import { SettingField } from "@/components/settings/SettingField";
import { EventsCard } from "@/components/settings/EventsCard";
import { AmberNotice, Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isError } from "@/lib/frappe";
import {
  BACKDATING_FIELD,
  allFields,
  changePayload,
  isEditable,
  isMandatory,
  isVisible,
  livestockSettings,
  pendingChanges,
  saveLivestockSettings,
  showValue,
  visibleTabs,
  zeroWarnings,
  type LivestockSettingsDoc,
  type SettingsSection,
  type SettingsTableRow,
  type SettingsValue,
} from "@/lib/settings";

/**
 * Livestock Settings, on the phone and the laptop instead of only the desk.
 *
 * The page is a mirror of the doctype rather than a second copy of it: the
 * tabs, the sections, the order, the help text and the control for each field
 * all come from the meta the read endpoint forwards. Nothing here names a
 * field, with two deliberate exceptions — Backdating Open, which is not a tick
 * box like any other, and the three child tables, which are shown and not
 * edited.
 *
 * Saving is explicit and narrow. The page keeps a draft, shows exactly which
 * settings changed and from what, and sends only those. It never sends the
 * whole document: writing all fifty fields back to re-save one of them is how
 * unset values get coerced to 0 and how every age and interval guard on the
 * farm gets switched off at once — which has happened here before.
 */
/** The Events tab: not a doctype tab, so a name no doctype tab can have. */
const EVENTS_TAB = "__events";

export function Settings() {
  const [doc, setDoc] = useState<LivestockSettingsDoc | null>(null);
  const [draft, setDraft] = useState<Record<string, SettingsValue>>({});
  /** Edited lists, by table fieldname. Saved with the scalars, in one call. */
  const [tableDraft, setTableDraft] = useState<Record<string, SettingsTableRow[]>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  /** Whatever the server last said. Never reworded. */
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState<string[] | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const result = await livestockSettings();
    setLoading(false);
    if (isError(result)) {
      setFailure(result.error);
      return;
    }
    setFailure(null);
    setDoc(result);
    setDraft({});
    setTableDraft({});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const fields = useMemo(() => allFields(doc), [doc]);
  // A user who may edit only part of the page (an Accounts Manager: the
  // Accounts & Insurance tab) is shown that part, not a farm's worth of rules
  // they cannot touch. Whoever may only read sees every tab, read-only.
  const tabs = useMemo(() => visibleTabs(doc), [doc]);
  const values = doc?.values || {};
  const changes = useMemo(
    () => pendingChanges(fields, values, draft),
    [fields, values, draft],
  );
  const dirtyTables = useMemo(
    () =>
      Object.keys(tableDraft).filter((name) => {
        const table = doc?.tables.find((t) => t.fieldname === name);
        return table && tableDirty(tableDraft[name], table.rows);
      }),
    [doc, tableDraft],
  );
  const unsaved = changes.length + dirtyTables.length;
  const zeros = useMemo(() => zeroWarnings(fields, values, draft), [fields, values, draft]);
  // Nothing at all is writable: no full write and no per-field grant.
  const readOnly = !doc?.can_write && !(doc?.writable && doc.writable.length > 0);

  function edit(fieldname: string, next: SettingsValue) {
    setSaved(null);
    setDraft((d) => ({ ...d, [fieldname]: next }));
  }

  async function save() {
    if (!unsaved) return;
    setSaving(true);
    setFailure(null);
    setSaved(null);
    const lists: Record<string, SettingsTableRow[]> = {};
    for (const name of dirtyTables) lists[name] = tableDraft[name];
    const result = await saveLivestockSettings(changePayload(changes), lists);
    setSaving(false);
    if (isError(result)) {
      // The server's words, unchanged — it names the field and says why.
      setFailure(result.error);
      return;
    }
    setSaved(Object.keys(result.changed || {}));
    setDoc((current) =>
      current
        ? {
            ...current,
            values: result.values,
            tables: current.tables.map((t) =>
              result.tables?.[t.fieldname] ? { ...t, rows: result.tables[t.fieldname].rows } : t,
            ),
          }
        : current,
    );
    setDraft({});
    setTableDraft({});
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Configuration" title="Settings">
        Every rule on this page applies to the whole farm, not to one animal or one run.
        Change is deliberate: edit what you need, read the list of what changed, then save.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      {saved && (
        <Notice tone="ok">
          {saved.length === 0
            ? "Nothing had actually changed, so nothing was written."
            : `Saved: ${saved.join(", ")}.`}
        </Notice>
      )}

      {readOnly && doc && (
        <Notice tone="info">
          You can read these settings but not change them. Saving is left off rather than
          offered and refused.
        </Notice>
      )}

      {zeros.length > 0 && (
        <AmberNotice>
          <p className="font-semibold">
            {zeros.length === 1 ? "A rule is set to 0" : `${zeros.length} rules are set to 0`}
          </p>
          <p className="mt-1">
            A 0 here is not an empty setting. The guards read it as “rule off”: the check
            simply stops applying, farm-wide, and nothing says so at the moment somebody
            records the event it would have caught.
          </p>
          <ul className="mt-2 list-disc pl-5">
            {zeros.map((warning) => (
              <li key={warning.field.fieldname}>
                <span className="font-medium">{warning.field.label}</span>
                {warning.rule === "disables"
                  ? " — 0 switches this rule off. If you meant “no value”, that is not what it does."
                  : " — 0 is never valid on this field; saving it will be refused."}
                {warning.stored ? " (already stored)" : " (typed, not saved)"}
              </li>
            ))}
          </ul>
        </AmberNotice>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-[13px] text-[var(--sd-muted)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Reading Livestock Settings…
        </div>
      )}

      {doc && (
        <Tabs defaultValue={tabs[0]?.fieldname} className="flex flex-col gap-5">
          <TabsList className="flex-wrap self-start">
            {tabs.map((tab) => (
              <TabsTrigger key={tab.fieldname} value={tab.fieldname}>
                {tab.label}
              </TabsTrigger>
            ))}
            {doc.can_write && <TabsTrigger value={EVENTS_TAB}>Events</TabsTrigger>}
          </TabsList>

          {/* Which events the farm records, and each one's stock and timing.
              The switch and the stock rule live on each Livestock Event Type,
              not on this doctype, so the tab is the page's own. */}
          {doc.can_write && <TabsContent value={EVENTS_TAB}>
            <EventsCard
              canWrite={!!doc.can_write}
              fields={fields}
              values={values}
              onSettingsSaved={(next) =>
                setDoc((current) => (current ? { ...current, values: next } : current))
              }
            />
          </TabsContent>}

          {tabs.map((tab) => (
            <TabsContent key={tab.fieldname} value={tab.fieldname}>
              <div className="flex flex-col gap-5">
                {tab.sections.map((section) => (
                  <SectionCard
                    key={section.fieldname}
                    section={section}
                    doc={doc}
                    draft={draft}
                    onEdit={edit}
                    readOnly={readOnly}
                    tableDraft={tableDraft}
                    onTableEdit={(name, rows) => {
                      setSaved(null);
                      setTableDraft((d) => ({ ...d, [name]: rows }));
                    }}
                  />
                ))}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      )}

      {doc && !readOnly && (
        <div className="sticky bottom-0 z-20 -mx-4 border-t border-[var(--sd-line)] bg-[var(--sd-card)]/95 px-4 py-3 backdrop-blur md:-mx-6 md:px-6">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-[13px] font-medium text-[var(--sd-ink)]">
                {unsaved === 0
                  ? "No unsaved changes"
                  : `${unsaved} unsaved ${unsaved === 1 ? "change" : "changes"}`}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={unsaved === 0 || saving}
                  onClick={() => {
                    setDraft({});
                    setTableDraft({});
                    setSaved(null);
                  }}
                >
                  Discard
                </Button>
                <Button size="sm" disabled={unsaved === 0 || saving} onClick={save}>
                  {saving
                    ? "Saving…"
                    : `Save ${unsaved || ""} ${unsaved === 1 ? "change" : "changes"}`.trim()}
                </Button>
              </div>
            </div>

            {unsaved > 0 && (
              <ul className="flex flex-col gap-1 text-[12px] text-[var(--sd-muted)]">
                {dirtyTables.map((name) => (
                  <li key={name} className="flex gap-1.5">
                    <span className="font-medium text-[var(--sd-ink)]">
                      {doc?.tables.find((t) => t.fieldname === name)?.label ?? name}
                    </span>
                    <span>list edited</span>
                  </li>
                ))}
                {changes.map((change) => (
                  <li key={change.field.fieldname} className="flex flex-wrap items-center gap-1.5">
                    {change.field.fieldname === BACKDATING_FIELD && (
                      <ShieldAlert className="h-3.5 w-3.5 text-[var(--sd-amber)]" />
                    )}
                    <span className="font-medium text-[var(--sd-ink)]">
                      {change.field.label}
                    </span>
                    <span>{showValue(change.field, change.from)}</span>
                    <span aria-hidden>→</span>
                    <span className="font-medium text-[var(--sd-ink)]">
                      {showValue(change.field, change.to)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Page>
  );
}

function SectionCard({
  section,
  doc,
  draft,
  onEdit,
  readOnly,
  tableDraft,
  onTableEdit,
}: {
  section: SettingsSection;
  doc: LivestockSettingsDoc;
  draft: Record<string, SettingsValue>;
  onEdit: (fieldname: string, next: SettingsValue) => void;
  readOnly: boolean;
  tableDraft: Record<string, SettingsTableRow[]>;
  onTableEdit: (fieldname: string, rows: SettingsTableRow[]) => void;
}) {
  const tables = doc.tables.filter(
    (t) => section.tables.includes(t.fieldname) && isVisible(t, doc.values, draft),
  );
  const visible = section.fields.filter((f) => isVisible(f, doc.values, draft));
  if (!visible.length && !tables.length) return null;

  const backdating = visible.filter((f) => f.fieldname === BACKDATING_FIELD);
  const ordinary = visible.filter((f) => f.fieldname !== BACKDATING_FIELD);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-[15px]">{section.label || "Settings"}</CardTitle>
        {section.description && <CardDescription>{section.description}</CardDescription>}
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {ordinary.length > 0 && (
          <div className="grid gap-x-8 gap-y-5 md:grid-cols-2 xl:grid-cols-3">
            {ordinary.map((field) => (
              <SettingField
                key={field.fieldname}
                field={field}
                stored={doc.values[field.fieldname] ?? null}
                value={
                  field.fieldname in draft
                    ? draft[field.fieldname]
                    : (doc.values[field.fieldname] ?? null)
                }
                onChange={(next) => onEdit(field.fieldname, next)}
                disabled={!isEditable(field, doc, doc.values, draft)}
                required={isMandatory(field, doc.values, draft)}
              />
            ))}
          </div>
        )}

        {backdating.map((field) => (
          <BackdatingSetting
            key={field.fieldname}
            field={field}
            value={
              field.fieldname in draft
                ? draft[field.fieldname]
                : (doc.values[field.fieldname] ?? null)
            }
            onChange={(next) => onEdit(field.fieldname, next)}
            disabled={!isEditable(field, doc, doc.values, draft)}
          />
        ))}

        {tables.length > 0 && ordinary.length > 0 && <Separator />}

        {tables.map((table) => (
          <ChildTableEditor
            key={table.fieldname}
            table={table}
            rows={tableDraft[table.fieldname] ?? table.rows}
            onChange={(rows) => onTableEdit(table.fieldname, rows)}
            canWrite={isEditable({ fieldname: table.fieldname, read_only: table.read_only }, doc, doc.values, draft)}
          />
        ))}

        {section.fieldname === "sb_appreciation" && can.flag("appreciate") && <AppreciationRun canRun />}
      </CardContent>
    </Card>
  );
}
