import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, ShieldAlert } from "lucide-react";
import { BackdatingSetting } from "@/components/settings/BackdatingSetting";
import { ChildTableView } from "@/components/settings/ChildTableView";
import { SettingField } from "@/components/settings/SettingField";
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
  isVisible,
  livestockSettings,
  pendingChanges,
  saveLivestockSettings,
  showValue,
  zeroWarnings,
  type LivestockSettingsDoc,
  type SettingsSection,
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
export function Settings() {
  const [doc, setDoc] = useState<LivestockSettingsDoc | null>(null);
  const [draft, setDraft] = useState<Record<string, SettingsValue>>({});
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
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const fields = useMemo(() => allFields(doc), [doc]);
  const values = doc?.values || {};
  const changes = useMemo(
    () => pendingChanges(fields, values, draft),
    [fields, values, draft],
  );
  const zeros = useMemo(() => zeroWarnings(fields, values, draft), [fields, values, draft]);
  const readOnly = !doc?.can_write;

  function edit(fieldname: string, next: SettingsValue) {
    setSaved(null);
    setDraft((d) => ({ ...d, [fieldname]: next }));
  }

  async function save() {
    if (!changes.length) return;
    setSaving(true);
    setFailure(null);
    setSaved(null);
    const result = await saveLivestockSettings(changePayload(changes));
    setSaving(false);
    if (isError(result)) {
      // The server's words, unchanged — it names the field and says why.
      setFailure(result.error);
      return;
    }
    setSaved(Object.keys(result.changed || {}));
    setDoc((current) => (current ? { ...current, values: result.values } : current));
    setDraft({});
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
        <Tabs defaultValue={doc.tabs[0]?.fieldname} className="flex flex-col gap-5">
          <TabsList className="flex-wrap self-start">
            {doc.tabs.map((tab) => (
              <TabsTrigger key={tab.fieldname} value={tab.fieldname}>
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {doc.tabs.map((tab) => (
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
                {changes.length === 0
                  ? "No unsaved changes"
                  : `${changes.length} unsaved ${changes.length === 1 ? "change" : "changes"}`}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={changes.length === 0 || saving}
                  onClick={() => {
                    setDraft({});
                    setSaved(null);
                  }}
                >
                  Discard
                </Button>
                <Button size="sm" disabled={changes.length === 0 || saving} onClick={save}>
                  {saving
                    ? "Saving…"
                    : `Save ${changes.length || ""} ${
                        changes.length === 1 ? "change" : "changes"
                      }`.trim()}
                </Button>
              </div>
            </div>

            {changes.length > 0 && (
              <ul className="flex flex-col gap-1 text-[12px] text-[var(--sd-muted)]">
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
}: {
  section: SettingsSection;
  doc: LivestockSettingsDoc;
  draft: Record<string, SettingsValue>;
  onEdit: (fieldname: string, next: SettingsValue) => void;
  readOnly: boolean;
}) {
  const tables = doc.tables.filter((t) => section.tables.includes(t.fieldname));
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
                disabled={readOnly}
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
            disabled={readOnly}
          />
        ))}

        {tables.length > 0 && ordinary.length > 0 && <Separator />}

        {tables.map((table) => (
          <ChildTableView key={table.fieldname} table={table} />
        ))}
      </CardContent>
    </Card>
  );
}
