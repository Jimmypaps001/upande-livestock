import { useState } from "react";
import { ShieldAlert, Unlock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { SettingsField, SettingsValue } from "@/lib/settings";

/**
 * The one setting on this page that turns the site's guards off.
 *
 * While Backdating Open is on, a backdated record skips the age, interval and
 * duplicate checks in `serverscripts/common/guards.py` — for every user, every
 * event type, farm-wide. It exists so a history load can be entered at all, and
 * it is meant to be turned off again afterwards.
 *
 * It is not drawn like the other tick box on this page, because it is not like
 * the other tick box. The switch is inert until the operator asks for it, and
 * what it actually does is written out beside it rather than left to the
 * doctype's one-line description. Anybody may still change it — that is what
 * the setting is for — but not by brushing past a toggle on the way to
 * something else.
 */
export function BackdatingSetting({
  field,
  value,
  onChange,
  disabled,
}: {
  field: SettingsField;
  value: SettingsValue;
  onChange: (next: SettingsValue) => void;
  disabled?: boolean;
}) {
  const [unlocked, setUnlocked] = useState(false);
  const on = Number(value ?? 0) === 1;

  return (
    <div className="flex flex-col gap-3 rounded-[var(--sd-radius-lg)] border border-[var(--sd-amber-line)] bg-[var(--sd-amber-bg)] px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="flex items-center gap-2 text-[13px] font-semibold text-[var(--sd-amber)]">
            <ShieldAlert className="h-4 w-4 shrink-0" />
            {field.label} — {on ? "guards are off for backdated records" : "guards are on"}
          </span>
          <p className="max-w-[52rem] text-[12px] leading-relaxed text-[var(--sd-amber)]">
            While this is on, a record entered with a past date skips every age, interval
            and duplicate check — a service on an animal too young, a second calving inside
            the minimum interval, the same event twice. Records dated today are still
            checked. It is meant to be on only while a history load is being entered, and
            turned off when that finishes.
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <Switch
            checked={on}
            disabled={disabled || !unlocked}
            onCheckedChange={(next) => onChange(next ? 1 : 0)}
          />
          <span className="text-[13px] font-medium text-[var(--sd-amber)]">
            {on ? "On" : "Off"}
          </span>
        </div>
      </div>

      {!disabled && !unlocked && (
        <div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setUnlocked(true)}
            className="border-[var(--sd-amber-line)] text-[var(--sd-amber)]"
          >
            <Unlock className="h-3.5 w-3.5" />
            Let me change this
          </Button>
        </div>
      )}
    </div>
  );
}
