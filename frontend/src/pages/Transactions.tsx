import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, Loader2, X } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { isError } from "@/lib/frappe";
import { usePostingDay } from "@/lib/posting-day";
import {
  fetchStockCalendar,
  fetchStockDay,
  fetchStockDrafts,
  postStockDraft,
  type DayCounts,
  type StockEntryRow,
} from "@/lib/transactions";
import { cn, parseYmd, todayISO, ymd } from "@/lib/utils";

/**
 * The stock the farm's records moved, and what is still waiting on the store.
 *
 * An event recorded today when the store could not cover it still stands; its
 * Stock Entry is saved as a draft (common/stock). The list in the middle starts
 * as every draft still waiting; the calendar on the right marks each day — an
 * orange dot where a draft is waiting, a green dot where everything posted —
 * and picking a day lists that day's entries, drafts and posted alike. A draft
 * the store can now cover is posted from here, dated today, because the stock
 * was not there on the day.
 */

function dayLabel(iso: string) {
  const d = parseYmd(iso);
  return d ? d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : iso;
}

/** The days a month view shows, outside days included (≤ 42). */
function visibleRange(month: Date): [string, string] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const lead = (first.getDay() + 6) % 7;
  const trail = 6 - ((last.getDay() + 6) % 7);
  return [
    ymd(new Date(first.getFullYear(), first.getMonth(), 1 - lead)),
    ymd(new Date(last.getFullYear(), last.getMonth(), last.getDate() + trail)),
  ];
}

// The dot under a day number, drawn by the day cell itself so the calendar
// component needs nothing of its own.
const DOT =
  "after:pointer-events-none after:absolute after:bottom-0 after:left-1/2 after:size-1.5 after:-translate-x-1/2 after:rounded-full";
const ORANGE = "after:bg-[var(--sd-data-amber)]";
const GREEN = "after:bg-[var(--sd-data-green)]";

function StatusBadge({ entry }: { entry: StockEntryRow }) {
  const [label, tone] =
    entry.status === "Posted"
      ? ["Posted", "bg-[var(--sd-alert-ok)] text-[#1f7a3d]"]
      : entry.can_post
        ? ["Ready to post", "bg-[var(--sd-alert-ok)] text-[#1f7a3d]"]
        : ["Waiting for stock", "bg-[var(--sd-amber-bg)] text-[var(--sd-amber)]"];
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11.5px] font-medium", tone)}>
      {label}
    </span>
  );
}

function EntryRow({
  entry,
  busy,
  onPost,
}: {
  entry: StockEntryRow;
  busy: boolean;
  onPost: (e: StockEntryRow) => void;
}) {
  const draft = entry.status === "Draft";
  return (
    <li className="flex flex-col gap-2 border-t border-[var(--sd-line)] px-5 py-3 first:border-t-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-2.5">
          <span
            aria-hidden
            className={cn(
              "mt-1.5 size-2 shrink-0 rounded-full",
              draft ? "bg-[var(--sd-data-amber)]" : "bg-[var(--sd-data-green)]",
            )}
          />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[14px] font-semibold text-[var(--sd-ink)]">{entry.label ?? entry.stock_entry_type}</span>
              <StatusBadge entry={entry} />
            </div>
            <div className="mt-0.5 text-[12.5px] text-[var(--sd-muted)]">
              {entry.source?.animal || entry.source?.herd ? `${entry.source.animal || entry.source.herd} · ` : ""}
              {entry.source?.name ?? "record no longer found"} · {dayLabel(entry.posting_date)} · {entry.made_by}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <a
            href={`/app/stock-entry/${encodeURIComponent(entry.name)}`}
            className="inline-flex items-center gap-1 text-[12.5px] text-[var(--sd-muted)] hover:text-[var(--sd-ink)]"
          >
            {entry.name} <ExternalLink className="h-3 w-3" />
          </a>
          {draft && (
            <Button
              type="button"
              size="sm"
              variant={entry.can_post ? "default" : "outline"}
              disabled={!entry.can_post || busy}
              onClick={() => onPost(entry)}
              title={entry.can_post ? "Take the items out of the store now" : (entry.short ?? undefined)}
            >
              {busy && <Loader2 className="animate-spin" />}
              Post
            </Button>
          )}
        </div>
      </div>
      <ul className="flex flex-col gap-0.5 pl-[18px] text-[13px] text-[var(--sd-text)]">
        {entry.items.map((i, n) => (
          <li key={n}>
            {i.item_name || i.item_code} — {i.qty} {i.uom} from {i.warehouse}
          </li>
        ))}
      </ul>
      {entry.short && <p className="pl-[18px] text-[12.5px] text-[var(--sd-amber)]">Still short: {entry.short}</p>}
    </li>
  );
}

export function Transactions() {
  const postingDay = usePostingDay();
  // The server's today, not the browser's: entries are dated by the server.
  const today = postingDay?.today ?? todayISO();
  const toast = useToast();

  const [month, setMonth] = useState<Date>(() => {
    const t = parseYmd(todayISO()) ?? new Date();
    return new Date(t.getFullYear(), t.getMonth(), 1);
  });
  const [days, setDays] = useState<Record<string, DayCounts>>({});
  // No day picked: the list is every draft still waiting.
  const [picked, setPicked] = useState<string | null>(null);
  const [entries, setEntries] = useState<StockEntryRow[] | null>(null);
  const [waiting, setWaiting] = useState<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  // Follow the server's month once it answers.
  useEffect(() => {
    const t = postingDay && parseYmd(postingDay.today);
    if (t) setMonth(new Date(t.getFullYear(), t.getMonth(), 1));
  }, [postingDay]);

  const loadDays = useCallback(async (m: Date) => {
    const [from, to] = visibleRange(m);
    const r = await fetchStockCalendar(from, to);
    if (!isError(r)) setDays(r.days);
  }, []);

  const countWaiting = useCallback(async () => {
    const r = await fetchStockDrafts();
    if (isError(r)) return null;
    setWaiting(r.drafts.length);
    return r.drafts;
  }, []);

  const loadList = useCallback(
    async (day: string | null) => {
      setLoading(true);
      if (day) {
        const [r] = await Promise.all([fetchStockDay(day), countWaiting()]);
        setLoading(false);
        if (isError(r)) return setFailure(r.error);
        setFailure(null);
        setEntries(r.entries);
      } else {
        const r = await fetchStockDrafts();
        setLoading(false);
        if (isError(r)) return setFailure(r.error);
        setFailure(null);
        setEntries(r.drafts);
        setWaiting(r.drafts.length);
      }
    },
    [countWaiting],
  );

  useEffect(() => {
    void loadDays(month);
  }, [month, loadDays]);

  useEffect(() => {
    void loadList(picked);
  }, [picked, loadList]);

  const refresh = useCallback(() => {
    void loadDays(month);
    void loadList(picked);
  }, [loadDays, loadList, month, picked]);

  const post = useCallback(
    async (e: StockEntryRow) => {
      setBusy(e.name);
      const r = await postStockDraft(e.name);
      setBusy(null);
      if (isError(r)) toast(r.error, "error");
      else toast(`${e.name} posted — the items have left the store.`, "ok");
      refresh();
    },
    [refresh, toast],
  );

  // A day with any draft is orange, even if it also posted something: the
  // dot answers "is anything still waiting from this day".
  const modifiers = useMemo(() => {
    const draft: Date[] = [];
    const posted: Date[] = [];
    for (const [iso, c] of Object.entries(days)) {
      const d = parseYmd(iso);
      if (!d) continue;
      if (c.draft > 0) draft.push(d);
      else if (c.posted > 0) posted.push(d);
    }
    return { draft, posted };
  }, [days]);

  const drafts = entries?.filter((e) => e.status === "Draft").length ?? 0;
  const ready = entries?.filter((e) => e.can_post).length ?? 0;
  const title = picked ? dayLabel(picked) : "Waiting for stock";
  const description =
    entries === null
      ? "Loading…"
      : picked
        ? entries.length
          ? `${entries.length} transaction${entries.length === 1 ? "" : "s"} · ${drafts} in draft`
          : "No livestock stock moved on this day."
        : entries.length
          ? `${entries.length} draft${entries.length === 1 ? "" : "s"} · ${ready} ready to post`
          : "Nothing is waiting — every record's stock has been posted.";

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Stock" title="Transactions">
        <p className="max-w-2xl text-[14px] leading-relaxed text-[var(--sd-muted)]">
          The stock the farm&rsquo;s records moved. A record the store could not cover on the day still
          stands; its stock entry waits as a draft until the items are in, and is posted from here.
        </p>
      </PageHeading>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_auto]">
        <Card className="order-2 lg:order-1">
          <CardHeader className="flex flex-row items-start justify-between gap-3">
            <div>
              <CardTitle>{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </div>
            <div className="flex items-center gap-1">
              {picked && (
                <Button type="button" variant="outline" size="sm" onClick={() => setPicked(null)}>
                  <X /> Everything waiting{waiting ? ` (${waiting})` : ""}
                </Button>
              )}
              <RefreshButton onClick={refresh} loading={loading} label="the transactions" />
            </div>
          </CardHeader>
          <CardContent className="px-0 pb-2">
            {failure ? (
              <div className="px-6">
                <Notice tone="error">{failure}</Notice>
              </div>
            ) : entries?.length ? (
              <ul aria-label="Transactions" className="border-t border-[var(--sd-line)]">
                {entries.map((e) => (
                  <EntryRow key={e.name} entry={e} busy={busy === e.name} onPost={post} />
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>

        <Card className="order-1 lg:sticky lg:top-4 lg:order-2">
          <CardContent className="flex flex-col items-center gap-1 p-2">
            <Calendar
              mode="single"
              month={month}
              onMonthChange={setMonth}
              selected={picked ? parseYmd(picked) : undefined}
              onSelect={(d) => setPicked(d ? ymd(d) : null)}
              today={parseYmd(today)}
              modifiers={modifiers}
              modifiersClassNames={{ draft: cn(DOT, ORANGE), posted: cn(DOT, GREEN) }}
              // The picked day is the ink pill, so it reads apart from today's tint.
              classNames={{
                selected:
                  "rounded-full [&>button]:bg-[var(--sd-ink)] [&>button]:font-medium [&>button]:text-white [&>button]:hover:bg-[var(--sd-ink)] [&>button]:hover:text-white",
              }}
            />
            <div className="flex w-full flex-col gap-1 px-3 pb-2 text-[12px] text-[var(--sd-muted)]">
              <span className="flex items-center gap-2">
                <span className="size-2 rounded-full bg-[var(--sd-data-amber)]" /> A draft is waiting
              </span>
              <span className="flex items-center gap-2">
                <span className="size-2 rounded-full bg-[var(--sd-data-green)]" /> Everything posted
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}
