import { useCallback, useEffect, useState } from "react";
import { Bell, Check, CheckCheck, Loader2 } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CATEGORY_LABEL,
  fetchNotifications,
  markRead,
  relativeTime,
  type LivestockCategory,
  type LivestockNotification,
} from "@/lib/notifications-api";
import { cn } from "@/lib/utils";

/**
 * What the farm is being told, and has not dealt with.
 *
 * Every row here is a `Livestock Alert` somebody is responsible for — an animal
 * due to move, a cow close to calving, a pregnancy check nobody recorded. It is
 * deliberately NOT a feed of animal events: several thousand milkings, weighings
 * and drug issues are recorded here every week, and a bell that rang for each
 * would be switched off within days. Things that are DUE, OVERDUE or need a
 * decision earn a notification; things that merely happened do not.
 *
 * Reading a row marks it read and nothing else. There is no "action" button
 * because actioning an alert is a decision with an outcome and notes, and that
 * still belongs on the Livestock Alert record in the desk — a one-tap "done"
 * here would let somebody clear the farm's whole worklist by scrolling.
 */

const TABS: Array<{ value: LivestockCategory | ""; label: string }> = [
  { value: "", label: "All" },
  { value: "movement", label: CATEGORY_LABEL.movement },
  { value: "breeding", label: CATEGORY_LABEL.breeding },
  { value: "feed", label: CATEGORY_LABEL.feed },
];

function Pill({
  on,
  onClick,
  children,
}: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "h-7 rounded-full border px-3 text-[12px] font-medium transition-colors",
        on
          ? "border-[var(--sd-ink)] bg-[var(--sd-ink)] text-white"
          : "border-[var(--sd-line)] text-[var(--sd-muted)] hover:bg-[var(--sd-bg-soft)]",
      )}
    >
      {children}
    </button>
  );
}

function Row({
  item,
  onOpen,
}: {
  item: LivestockNotification;
  onOpen: (n: LivestockNotification) => void;
}) {
  const overdue = item.severity === "Overdue";
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      className={cn(
        "flex w-full items-start gap-3 rounded-[var(--sd-radius-lg)] border px-3 py-2.5 text-left transition-colors hover:bg-[var(--sd-bg-soft)]",
        item.read
          ? "border-[var(--sd-line)] bg-transparent"
          : "border-[var(--sd-line)] bg-[var(--sd-bg-soft)]",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "mt-1.5 h-2 w-2 shrink-0 rounded-full",
          item.read ? "bg-transparent" : overdue ? "bg-red-500" : "bg-[var(--sd-ink)]",
        )}
      />
      <span className="min-w-0 flex-1">
        {/* Escaped server-side when the notification is written — see
            common/notifications._subject. */}
        <span
          className={cn(
            "block text-[13px] leading-snug",
            item.read ? "text-[var(--sd-muted)]" : "font-medium text-[var(--sd-ink)]",
          )}
          dangerouslySetInnerHTML={{ __html: item.subject }}
        />
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--sd-quiet)]">
          {item.alert_kind && (
            <span
              className={cn(
                "rounded-full px-1.5 py-px ring-1",
                overdue
                  ? "text-red-600 ring-red-200"
                  : "text-[var(--sd-muted)] ring-[var(--sd-line)]",
              )}
            >
              {item.alert_kind}
            </span>
          )}
          {item.herd && <span>{item.herd}</span>}
          <span className="tabular-nums">{relativeTime(item.creation)}</span>
          {item.read ? <Check className="h-3 w-3" /> : null}
        </span>
      </span>
    </button>
  );
}

export function Notifications() {
  const [category, setCategory] = useState<LivestockCategory | "">("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [rows, setRows] = useState<LivestockNotification[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState("");
  const [clearing, setClearing] = useState(false);

  const load = useCallback(async () => {
    const r = await fetchNotifications({ category, unreadOnly, limit: 100 });
    setError(r.error || "");
    setRows(r.notifications);
    setUnread(r.unread);
  }, [category, unreadOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  const onOpen = async (n: LivestockNotification) => {
    if (n.read) return;
    setRows((prev) => (prev ?? []).map((r) => (r.name === n.name ? { ...r, read: 1 } : r)));
    setUnread(await markRead({ names: [n.name] }));
  };

  const onClearAll = async () => {
    setClearing(true);
    setUnread(await markRead({ all: true }));
    setRows((prev) => (prev ?? []).map((r) => ({ ...r, read: 1 })));
    setClearing(false);
    if (unreadOnly) void load();
  };

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock" title="Notifications">
        What the herd needs somebody to do — animals due to move, cows close to
        calving, pregnancy checks nobody has recorded. Routine events are not
        listed here.
      </PageHeading>

      {error && <Notice tone="error">{error}</Notice>}

      <div className="flex flex-wrap items-center gap-2">
        {TABS.map((t) => (
          <Pill key={t.value || "all"} on={category === t.value} onClick={() => setCategory(t.value)}>
            {t.label}
          </Pill>
        ))}
        <span className="mx-1 h-4 w-px bg-[var(--sd-line)]" />
        <Pill on={unreadOnly} onClick={() => setUnreadOnly((v) => !v)}>
          Unread only
        </Pill>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="ml-auto h-7 gap-1.5 text-[12px]"
          disabled={!unread || clearing}
          onClick={onClearAll}
        >
          {clearing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <CheckCheck className="h-3.5 w-3.5" />
          )}
          {unread ? `Mark ${unread} read` : "Nothing unread"}
        </Button>
      </div>

      {rows === null ? (
        <div className="flex flex-col gap-1.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-14 animate-pulse rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)]"
            />
          ))}
        </div>
      ) : !rows.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-[15px]">
              <Bell className="h-4 w-4 text-[var(--sd-quiet)]" />
              Nothing here
            </CardTitle>
            <CardDescription>
              {category || unreadOnly
                ? "Nothing matches these filters."
                : "Nothing is due or overdue. The nightly sweep raises alerts about herd movement, culling windows, calving dates, pregnancy checks and concentrate running low — they will appear here."}
            </CardDescription>
          </CardHeader>
          <CardContent className="text-[13px] text-[var(--sd-muted)]">
            <a
              href="/app/livestock-alert"
              className="font-medium text-[var(--sd-ink)] underline underline-offset-4"
            >
              Open every alert in the desk
            </a>
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-1.5">
          {rows.map((n) => (
            <Row key={n.name} item={n} onOpen={onOpen} />
          ))}
        </div>
      )}
    </Page>
  );
}
