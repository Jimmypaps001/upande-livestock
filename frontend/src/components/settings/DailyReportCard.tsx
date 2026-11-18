import { useCallback, useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SearchPicker } from "@/components/ui/search-picker";
import { Switch } from "@/components/ui/switch";
import { isError } from "@/lib/frappe";
import {
  dailyReportSettings,
  previewDailyReport,
  saveDailyReportSettings,
  sendDailyReportNow,
  type DailyReportDoc,
  type DailyReportState,
} from "@/lib/settings";

/**
 * The Daily Report tab: who gets the end-of-day email, and when.
 *
 * Each control saves as it is changed, and the page shows what the server
 * stored, so the recipient list under the controls is always the one the next
 * email will go to.
 */
export function DailyReportCard({ canWrite }: { canWrite: boolean }) {
  const [doc, setDoc] = useState<DailyReportDoc | null>(null);
  const [time, setTime] = useState("18:00");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const adopt = useCallback((state: DailyReportState) => {
    setDoc((d) => (d ? { ...d, ...state } : d));
    setTime(state.time);
  }, []);

  useEffect(() => {
    (async () => {
      const result = await dailyReportSettings();
      if (isError(result)) return setFailure(result.error);
      setDoc(result);
      setTime(result.time);
    })();
  }, []);

  async function save(changes: Parameters<typeof saveDailyReportSettings>[0]) {
    setBusy(true);
    setFailure(null);
    setInfo(null);
    const result = await saveDailyReportSettings(changes);
    setBusy(false);
    if (isError(result)) return setFailure(result.error);
    adopt(result);
  }

  async function sendNow() {
    setBusy(true);
    setFailure(null);
    setInfo(null);
    const result = await sendDailyReportNow();
    setBusy(false);
    if (isError(result)) return setFailure(result.error);
    setInfo(result.message);
  }

  async function showPreview() {
    setBusy(true);
    setFailure(null);
    const result = await previewDailyReport();
    setBusy(false);
    if (isError(result)) return setFailure(result.error);
    setPreview(result.html);
  }

  if (!doc) {
    return failure ? (
      <Notice tone="error">{failure}</Notice>
    ) : (
      <div className="flex items-center gap-2 text-[13px] text-[var(--sd-muted)]">
        <Loader2 className="h-4 w-4 animate-spin" />
        Reading the daily report settings…
      </div>
    );
  }

  const editable = canWrite && doc.can_write && !busy;
  const users = doc.options.users.map((u) => ({
    value: u.name,
    label: u.full_name ? `${u.full_name} (${u.name})` : u.name,
  }));

  return (
    <div className="flex flex-col gap-5">
      {failure && <Notice tone="error">{failure}</Notice>}
      {info && <Notice tone="ok">{info}</Notice>}

      <Card>
        <CardHeader>
          <CardTitle className="text-[15px]">Daily report</CardTitle>
          <CardDescription>
            An email each day, after the send time, telling the people below what happened on
            the farm that day: activities, weighings, health, drugs, movements and feeding.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <div className="flex items-center gap-3">
            <Switch
              id="report-enabled"
              checked={doc.enabled === 1}
              disabled={!editable}
              onCheckedChange={(on) => save({ enabled: on ? 1 : 0 })}
            />
            <Label htmlFor="report-enabled">
              {doc.enabled === 1 ? "The report is sent every day" : "The report is off"}
            </Label>
          </div>

          <div className="grid gap-x-8 gap-y-5 md:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="report-time">Send time</Label>
              <Input
                id="report-time"
                type="time"
                className="w-40"
                value={time}
                disabled={!editable}
                onChange={(e) => setTime(e.target.value)}
                onBlur={() => time && time !== doc.time && save({ time })}
              />
              <p className="text-[12px] text-[var(--sd-muted)]">
                Site time. It is sent once a day, at the first check after this time
                {doc.last_sent ? `. Last sent for ${doc.last_sent}.` : "."}
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="report-head">Livestock head</Label>
              <div className="flex items-center gap-2">
                <SearchPicker
                  id="report-head"
                  value={doc.head}
                  options={users}
                  placeholder="Choose a user…"
                  onChange={(head) => editable && save({ head })}
                />
                {doc.head && editable && (
                  <Button variant="ghost" size="sm" onClick={() => save({ head: "" })}>
                    Clear
                  </Button>
                )}
              </div>
              <p className="text-[12px] text-[var(--sd-muted)]">Always receives the report.</p>
            </div>

            <ChipList
              label="Recipient roles"
              hint="Every enabled user with any of these roles also receives it."
              chosen={doc.roles}
              options={doc.options.roles}
              disabled={!editable}
              onChange={(roles) => save({ roles })}
            />
            <ChipList
              label="Recipient role profiles"
              hint="Every enabled user on any of these role profiles also receives it."
              chosen={doc.role_profiles}
              options={doc.options.role_profiles}
              disabled={!editable}
              onChange={(role_profiles) => save({ role_profiles })}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" disabled={!editable} onClick={sendNow}>
              Send now
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={showPreview}>
              Preview
            </Button>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          </div>

          <div className="flex flex-col gap-1">
            <p className="text-[13px] font-medium">
              {doc.recipients.length === 1
                ? "1 person will receive it"
                : `${doc.recipients.length} people will receive it`}
            </p>
            {doc.recipients.length === 0 ? (
              <p className="text-[12px] text-[var(--sd-muted)]">
                Nobody yet. Choose a livestock head, a role or a role profile. Disabled users and
                users with no email address are left out.
              </p>
            ) : (
              <ul className="text-[12px] text-[var(--sd-muted)]">
                {doc.recipients.map((r) => (
                  <li key={r.user}>
                    {r.full_name} · {r.email}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </CardContent>
      </Card>

      {preview !== null && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-[15px]">Preview for today</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => setPreview(null)}>
              Close
            </Button>
          </CardHeader>
          <CardContent>
            {/* The server's own HTML, rendered in a frame so its styles stay inside it. */}
            <iframe title="Daily report preview" sandbox="" srcDoc={preview} className="h-[640px] w-full rounded-md border border-[var(--sd-line)] bg-white" />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ChipList({
  label,
  hint,
  chosen,
  options,
  disabled,
  onChange,
}: {
  label: string;
  hint: string;
  chosen: string[];
  options: string[];
  disabled: boolean;
  onChange: (next: string[]) => void;
}) {
  const remaining = options.filter((o) => !chosen.includes(o)).map((o) => ({ value: o, label: o }));
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {chosen.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chosen.map((name) => (
            <span
              key={name}
              className="inline-flex items-center gap-1 rounded-full border border-[var(--sd-line)] bg-[var(--sd-bg-soft)] px-2.5 py-0.5 text-[12px]"
            >
              {name}
              <button
                type="button"
                aria-label={`Remove ${name}`}
                disabled={disabled}
                className="text-[var(--sd-muted)] hover:text-[var(--sd-ink)] disabled:opacity-50"
                onClick={() => onChange(chosen.filter((c) => c !== name))}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      {!disabled && (
        <SearchPicker
          value=""
          options={remaining}
          placeholder={`Add to ${label.toLowerCase()}…`}
          onChange={(next) => next && onChange([...chosen, next])}
        />
      )}
      <p className="text-[12px] text-[var(--sd-muted)]">{hint}</p>
    </div>
  );
}
