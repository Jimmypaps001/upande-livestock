import { call, type Envelope } from "@/lib/frappe";

/**
 * Livestock Settings, as the page reads and writes it.
 *
 * The shapes below are the doctype's own meta, forwarded by the read endpoint —
 * nothing here lists the fifty fieldnames. A settings page with its own copy of
 * the field list stops being a mirror of the doctype the first time somebody
 * adds a field on the desk, and it fails silently: the new setting simply never
 * appears.
 *
 * The two rules this file exists to keep straight:
 *
 *  * **`null` is not `0`.** A field with no row reads back as `null` and means
 *    "the built-in default applies". A stored `0` means something else entirely
 *    — on the two fields the server marks `zero: "disables"` it switches the
 *    rule off, and on the rest it is the fault
 *    `repair_zeroed_age_interval_settings` exists to undo.
 *  * **Only real changes are sent.** `pendingChanges` compares against what the
 *    server last said, so saving after touching one box does not rewrite the
 *    other forty-nine.
 */

/* ── Wire shapes ───────────────────────────────────────────────────────── */

/** What a 0 in this box would mean. Decided on the server (see
 *  `serverscripts/settings/_shared.py: zero_rule`), never guessed here. */
export type ZeroRule = "disables" | "invalid" | null;

export type SettingsValue = string | number | null;

export type SettingsField = {
  fieldname: string;
  label: string;
  fieldtype: string;
  options: string | null;
  description: string | null;
  default: string | null;
  depends_on: string | null;
  reqd: boolean;
  zero: ZeroRule;
  /** True where a wrong value posts stock or money somewhere else rather than
   *  raising — the warehouse, item and account links. */
  posts: boolean;
};

export type SettingsSection = {
  fieldname: string;
  label: string | null;
  description: string | null;
  fields: SettingsField[];
  /** Fieldnames of the child tables that belong in this section. */
  tables: string[];
};

export type SettingsTab = {
  fieldname: string;
  label: string;
  sections: SettingsSection[];
};

export type SettingsTable = {
  fieldname: string;
  label: string;
  description: string | null;
  doctype: string;
  columns: SettingsField[];
  rows: Array<Record<string, unknown>>;
};

export type LivestockSettingsDoc = {
  ok: boolean;
  doctype: string;
  tabs: SettingsTab[];
  values: Record<string, SettingsValue>;
  tables: SettingsTable[];
  can_write: boolean;
};

export type SettingsChange = { from: SettingsValue; to: SettingsValue };

export type SaveResult = {
  ok: boolean;
  changed: Record<string, SettingsChange>;
  unchanged: string[];
  values: Record<string, SettingsValue>;
};

/* ── Endpoints ─────────────────────────────────────────────────────────── */

const READ = "upande_livestock.serverscripts.settings.livestock_settings.livestock_settings";
const SAVE =
  "upande_livestock.serverscripts.settings.save_livestock_settings.save_livestock_settings";

export function livestockSettings(): Promise<Envelope<LivestockSettingsDoc>> {
  return call(READ);
}

export function saveLivestockSettings(
  changes: Record<string, SettingsValue>,
): Promise<Envelope<SaveResult>> {
  return call(SAVE, { payload: changes });
}

/* ── The rules the screen must not break ───────────────────────────────── */

/** Fieldtypes whose value is a number, not a word. */
export const NUMERIC_FIELDTYPES = new Set(["Int", "Float", "Percent", "Currency"]);

/** The one setting that turns the site's guards off. Named here so the page can
 *  treat it as what it is rather than as another tick box. */
export const BACKDATING_FIELD = "custom_backdating_open";

export function isBlank(value: unknown): boolean {
  return value === null || value === undefined || String(value).trim() === "";
}

/** The value in force for a field: what the operator has typed, else what is
 *  stored. `0` is a value; only an untouched field falls through. */
export function effectiveValue(
  fieldname: string,
  values: Record<string, SettingsValue>,
  draft: Record<string, SettingsValue>,
): SettingsValue {
  return fieldname in draft ? draft[fieldname] : (values[fieldname] ?? null);
}

/**
 * Is the drafted value the same setting as the stored one?
 *
 * Compared by type, not by string: the box holds `"90"` where the server said
 * `90`, and re-sending every field that merely looks different as text is how a
 * one-field edit turns into a fifty-field write.
 */
export function sameValue(
  field: SettingsField,
  stored: SettingsValue,
  drafted: SettingsValue,
): boolean {
  if (field.fieldtype === "Check") return Number(stored ?? 0) === Number(drafted ?? 0);
  if (NUMERIC_FIELDTYPES.has(field.fieldtype)) {
    if (isBlank(stored) && isBlank(drafted)) return true;
    if (isBlank(stored) || isBlank(drafted)) return false;
    return Number(stored) === Number(drafted);
  }
  return String(stored ?? "").trim() === String(drafted ?? "").trim();
}

/** Every field on the document, flattened out of the tabs. */
export function allFields(doc: LivestockSettingsDoc | null): SettingsField[] {
  if (!doc) return [];
  return doc.tabs.flatMap((tab) => tab.sections.flatMap((section) => section.fields));
}

export type PendingChange = {
  field: SettingsField;
  from: SettingsValue;
  to: SettingsValue;
};

/**
 * What Save would send, and what the page shows before it sends it.
 *
 * An emptied numeric box is included deliberately rather than dropped: the
 * server answers "that needs a number, and 0 does not clear the rule, it
 * switches it off", which is the sentence the operator needs to read. Silently
 * skipping it would let them think they had cleared something.
 */
export function pendingChanges(
  fields: SettingsField[],
  values: Record<string, SettingsValue>,
  draft: Record<string, SettingsValue>,
): PendingChange[] {
  const byName = new Map(fields.map((f) => [f.fieldname, f]));
  const out: PendingChange[] = [];
  for (const fieldname of Object.keys(draft)) {
    const field = byName.get(fieldname);
    if (!field) continue;
    const stored = values[fieldname] ?? null;
    const drafted = draft[fieldname];
    if (sameValue(field, stored, drafted)) continue;
    out.push({ field, from: stored, to: drafted });
  }
  return out;
}

/** The patch itself, keyed the way the endpoint expects. */
export function changePayload(changes: PendingChange[]): Record<string, SettingsValue> {
  const payload: Record<string, SettingsValue> = {};
  for (const change of changes) payload[change.field.fieldname] = change.to;
  return payload;
}

export type ZeroWarning = {
  field: SettingsField;
  rule: Exclude<ZeroRule, null>;
  /** True when the 0 is already stored, rather than only typed. */
  stored: boolean;
};

/**
 * Every timing field sitting at 0 right now — typed or already stored.
 *
 * This is the warning the page exists to carry. `common/guards.py` reads a
 * configured 0 as "rule off", so a 0 in one of these boxes is not an empty
 * setting; it is the age, interval or duplicate check for that event switched
 * off for the whole farm. It has gone wrong here once already, which is why
 * `patches/repair_zeroed_age_interval_settings.py` exists.
 */
export function zeroWarnings(
  fields: SettingsField[],
  values: Record<string, SettingsValue>,
  draft: Record<string, SettingsValue>,
): ZeroWarning[] {
  const out: ZeroWarning[] = [];
  for (const field of fields) {
    if (!field.zero) continue;
    const current = effectiveValue(field.fieldname, values, draft);
    if (isBlank(current) || Number(current) !== 0) continue;
    out.push({
      field,
      rule: field.zero,
      stored: !isBlank(values[field.fieldname]) && Number(values[field.fieldname]) === 0,
    });
  }
  return out;
}

/** How a value reads in the change list. An unset field says so in words —
 *  showing nothing there would look like a blank the operator had typed. */
export function showValue(field: SettingsField, value: SettingsValue): string {
  if (field.fieldtype === "Check") return Number(value ?? 0) ? "On" : "Off";
  if (isBlank(value)) return "not set";
  return String(value);
}

/**
 * Whether a `depends_on` field should be shown.
 *
 * Only the plain-fieldname form is honoured — `"cull_bulls_after_birth"`, which
 * is the only form this doctype uses. An `eval:` expression is shown rather than
 * hidden: a setting the operator cannot see is worse than one shown at the
 * wrong moment, and this page will not run the desk's JavaScript to find out.
 */
export function isVisible(
  field: SettingsField,
  values: Record<string, SettingsValue>,
  draft: Record<string, SettingsValue>,
): boolean {
  const dep = (field.depends_on || "").trim();
  if (!dep || dep.startsWith("eval:")) return true;
  const current = effectiveValue(dep.replace(/^doc\./, ""), values, draft);
  return !isBlank(current) && Number(current) !== 0;
}
