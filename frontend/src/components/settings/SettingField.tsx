import { AlertTriangle, Coins } from "lucide-react";
import { LinkPicker } from "@/components/settings/LinkPicker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  NUMERIC_FIELDTYPES,
  isBlank,
  type SettingsField,
  type SettingsValue,
} from "@/lib/settings";

/**
 * One setting, drawn from the doctype's own description of it.
 *
 * The fieldtype decides the control and nothing else does, so a field added to
 * Livestock Settings on the desk turns up here with the right control and its
 * own help text without this file changing.
 *
 * Two things it says out loud that the desk does not:
 *
 *  * a numeric field with no stored value says "not set — the built-in default
 *    applies", rather than showing an empty box that looks like a value
 *    somebody deleted, and
 *  * a field sitting at 0 that a 0 switches off is marked at the field, not
 *    only in the summary at the top of the page. The operator reading that box
 *    is the one who needs to know.
 */
export function SettingField({
  field,
  stored,
  value,
  onChange,
  disabled,
}: {
  field: SettingsField;
  /** What the server last said, for the "not set" note. */
  stored: SettingsValue;
  value: SettingsValue;
  onChange: (next: SettingsValue) => void;
  disabled?: boolean;
}) {
  const id = `set-${field.fieldname}`;
  const numeric = NUMERIC_FIELDTYPES.has(field.fieldtype);
  const isZero = !isBlank(value) && Number(value) === 0 && !!field.zero;

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} className="flex flex-wrap items-center gap-2 text-[var(--sd-ink)]">
        <span>{field.label}</span>
        {field.posts && (
          <span
            title="A wrong value here does not error — it posts stock or money somewhere else."
            className="inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--sd-muted)]"
          >
            <Coins className="h-3 w-3" />
            Posts
          </span>
        )}
      </Label>

      {field.fieldtype === "Link" ? (
        <LinkPicker
          id={id}
          doctype={field.options || "DocType"}
          value={value === null || value === undefined ? null : String(value)}
          onChange={(next) => onChange(next)}
          disabled={disabled}
        />
      ) : field.fieldtype === "Check" ? (
        <div className="flex items-center gap-3 py-1">
          <Switch
            id={id}
            checked={Number(value ?? 0) === 1}
            disabled={disabled}
            onCheckedChange={(on) => onChange(on ? 1 : 0)}
          />
          <span className="text-[13px] text-[var(--sd-muted)]">
            {Number(value ?? 0) === 1 ? "On" : "Off"}
          </span>
        </div>
      ) : (
        <Input
          id={id}
          type={numeric ? "number" : "text"}
          inputMode={numeric ? "numeric" : undefined}
          min={numeric ? 0 : undefined}
          step={field.fieldtype === "Int" ? 1 : "any"}
          disabled={disabled}
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value)}
        />
      )}

      {field.description && (
        <p className="text-[11px] leading-relaxed text-[var(--sd-quiet)]">{field.description}</p>
      )}

      {numeric && isBlank(stored) && (
        <p className="text-[11px] text-[var(--sd-quiet)]">
          Not set — the built-in default applies
          {field.default ? ` (${field.default})` : ""}.
        </p>
      )}

      {isZero && (
        <p className="flex items-start gap-1.5 text-[11px] font-medium text-[var(--sd-amber)]">
          <AlertTriangle className="mt-px h-3 w-3 shrink-0" />
          {field.zero === "disables"
            ? "0 does not clear this — it switches the rule off. Nothing will be stopped by it."
            : "0 is not a setting on this field — it reads as “rule off”, and saving it will be refused."}
        </p>
      )}
    </div>
  );
}
