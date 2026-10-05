import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, ExternalLink, List, Loader2 } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isError } from "@/lib/frappe";
import { usePostingDay } from "@/lib/posting-day";
import { fetchStockDrafts, postStockDraft, type StockDraft } from "@/lib/transactions";
import { cn, parseYmd, todayISO, ymd } from "@/lib/utils";

/**
 * The stock the farm's records used and the store has not yet handed over.
 *
 * An event recorded today when the store could not cover it still stands; its
 * Stock Entry is saved as a draft (common/stock). Those drafts are here, on the
 * day they were recorded and as a list, each with what it is waiting for. Once
 * the store can cover one it is posted from here — today, because the stock was
 * not there on the day.
 */

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function monthLabel(d: Date) {
  return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function dayLabel(iso: string) {
  const d = parseYmd(iso);
  return d ? d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : iso;
}

/** The 6×7 grid of days the month sits in, Monday first. */
function monthGrid(month: Date): Date[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const lead = (first.getDay() + 6) % 7;
  const start = new Date(first.getFullYear(), first.getMonth(), 1 - lead);
  return Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
}

function eventOf(d: StockDraft) {
  return d.source?.event_type ?? d.stock_entry_type.replace(/^Livestock /, "");
}

function Status({ draft }: { draft: StockDraft }) {
  return draft.can_post ? (
    <span className="inline-flex items-center rounded-full bg-[var(--sd-alert-ok)] px-2 py-0.5 text-[11.5px] font-medium text-[#1f7a3d]">
      Ready to post
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full bg-[var(--sd-amber-bg)] px-2 py-0.5 text-[11.5px] font-medium text-[var(--sd-amber)]">
      Waiting for stock
    </span>
  );
}

function PostButton({ draft, busy, onPost }: { draft: StockDraft; busy: boolean; onPost: (d: StockDraft) => void }) {
  return (
    <Button
      type="button"
      size="sm"
      variant={draft.can_post ? "default" : "outline"}
      disabled={!draft.can_post || busy}
      onClick={() => onPost(draft)}
      title={draft.can_post ? "Take the items out of the store now" : (draft.short ?? undefined)}
    >
      {busy && <Loader2 className="animate-spin" />}
      Post
    </Button>
  );
}

function DraftCard({ draft, busy, onPost }: { draft: StockDraft; busy: boolean; onPost: (d: StockDraft) => void }) {
  return (
    <div className="flex flex-col gap-2 rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-card)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14px] font-semibold text-[var(--sd-ink)]">{draft.stock_entry_type}</span>
            <Status draft={draft} />
          </div>
          <div className="mt-0.5 text-[12.5px] text-[var(--sd-muted)]">
            {draft.source?.animal ? `${draft.source.animal} · ` : ""}
            {draft.source?.name ?? "record no longer found"} · {dayLabel(draft.posting_date)} · {draft.made_by}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={`/app/stock-entry/${encodeURIComponent(draft.name)}`}
            className="inline-flex items-center gap-1 text-[12.5px] text-[var(--sd-muted)] hover:text-[var(--sd-ink)]"
          >
            {draft.name} <ExternalLink className="h-3 w-3" />
          </a>
          <PostButton draft={draft} busy={busy} onPost={onPost} />
        </div>
      </div>
      <ul className="flex flex-col gap-0.5 text-[13px] text-[var(--sd-text)]">
        {draft.items.map((i, n) => (
          <li key={n}>
            {i.item_name || i.item_code} — {i.qty} {i.uom} from {i.warehouse}
          </li>
        ))}
      </ul>
      {draft.short && <p className="text-[12.5px] text-[var(--sd-amber)]">Still short: {draft.short}</p>}
    </div>
  );
}

function CalendarView({
  drafts,
  busy,
  onPost,
}: {
  drafts: StockDraft[];
  busy: string | null;
  onPost: (d: StockDraft) => void;
}) {
  // The server's today, not the browser's: a draft is dated by the server,
  // and a browser in another time zone would mark the wrong square as today.
  const day = usePostingDay();
  const today = day?.today ?? todayISO();
  const [month, setMonth] = useState(() => {
    const t = parseYmd(today) ?? new Date();
    return new Date(t.getFullYear(), t.getMonth(), 1);
  });
  const [picked, setPicked] = useState<string>(today);
  // When the server's answer lands after first paint, follow it — unless
  // somebody has already picked a day.
  const [touched, setTouched] = useState(false);
  useEffect(() => {
    if (!day || touched) return;
    const t = parseYmd(day.today);
    if (t) setMonth(new Date(t.getFullYear(), t.getMonth(), 1));
    setPicked(day.today);
  }, [day, touched]);

  const byDay = useMemo(() => {
    const m = new Map<string, StockDraft[]>();
    for (const d of drafts) m.set(d.posting_date, [...(m.get(d.posting_date) ?? []), d]);
    return m;
  }, [drafts]);

  const days = monthGrid(month);
  const shown = byDay.get(picked) ?? [];
  const step = (n: number) => setMonth((m) => new Date(m.getFullYear(), m.getMonth() + n, 1));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button type="button" variant="ghost" size="icon" aria-label="Previous month" onClick={() => step(-1)}>
            <ChevronLeft />
          </Button>
          <Button type="button" variant="ghost" size="icon" aria-label="Next month" onClick={() => step(1)}>
            <ChevronRight />
          </Button>
          <h3 className="ml-1 text-[15px] font-semibold text-[var(--sd-ink)]">{monthLabel(month)}</h3>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            const t = parseYmd(today) ?? new Date();
            setMonth(new Date(t.getFullYear(), t.getMonth(), 1));
            setPicked(today);
          }}
        >
          Today
        </Button>
      </div>

      <div className="overflow-x-auto rounded-md border border-[var(--sd-line)] bg-[var(--sd-card)]">
        <div role="grid" aria-label={`Drafts in ${monthLabel(month)}`} className="grid min-w-[42rem] grid-cols-7">
          {WEEKDAYS.map((w) => (
            <div
              key={w}
              role="columnheader"
              className="border-b border-[var(--sd-line)] px-2 py-2 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--sd-quiet)]"
            >
              {w}
            </div>
          ))}
          {days.map((d, i) => {
            const iso = ymd(d);
            const here = byDay.get(iso) ?? [];
            const inMonth = d.getMonth() === month.getMonth();
            return (
              <button
                key={iso}
                type="button"
                role="gridcell"
                aria-label={`${dayLabel(iso)}: ${here.length} draft${here.length === 1 ? "" : "s"}`}
                aria-selected={iso === picked}
                onClick={() => {
                  setTouched(true);
                  setPicked(iso);
                }}
                className={cn(
                  "flex min-h-[5.5rem] flex-col items-stretch gap-1 border-[var(--sd-line)] p-1.5 text-left transition-colors hover:bg-[var(--sd-bg-soft)]",
                  i % 7 !== 0 && "border-l",
                  i >= 7 && "border-t",
                  iso === picked && "bg-[var(--sd-bg-soft)] ring-1 ring-inset ring-[var(--sd-ink)]",
                )}
              >
                <span
                  className={cn(
                    "self-start rounded-full px-1.5 text-[12px] tabular-nums",
                    inMonth ? "text-[var(--sd-ink)]" : "text-[var(--sd-quiet)]",
                    iso === today && "bg-[var(--sd-ink)] text-white",
                  )}
                >
                  {d.getDate()}
                </span>
                {here.slice(0, 3).map((x) => (
                  <span
                    key={x.name}
                    className={cn(
                      "truncate rounded px-1.5 py-0.5 text-[11px]",
                      x.can_post
                        ? "bg-[var(--sd-alert-ok)] text-[#1f7a3d]"
                        : "bg-[var(--sd-amber-bg)] text-[var(--sd-amber)]",
                    )}
                  >
                    {eventOf(x)}
                    {x.source?.animal ? ` · ${x.source.animal}` : ""}
                  </span>
                ))}
                {here.length > 3 && (
                  <span className="px-1.5 text-[11px] text-[var(--sd-muted)]">+{here.length - 3} more</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-[13px] font-semibold text-[var(--sd-ink)]">{dayLabel(picked)}</h3>
        {shown.length ? (
          shown.map((d) => <DraftCard key={d.name} draft={d} busy={busy === d.name} onPost={onPost} />)
        ) : (
          <p className="text-[13px] text-[var(--sd-muted)]">Nothing waiting from this day.</p>
        )}
      </div>
    </div>
  );
}

function ListView({
  drafts,
  busy,
  onPost,
}: {
  drafts: StockDraft[];
  busy: string | null;
  onPost: (d: StockDraft) => void;
}) {
  const head = "px-3 py-2 text-left text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--sd-quiet)]";
  const cell = "px-3 py-2.5 align-top text-[13px] text-[var(--sd-text)]";
  return (
    <div className="overflow-x-auto rounded-md border border-[var(--sd-line)] bg-[var(--sd-card)]">
      <table className="w-full min-w-[56rem] border-collapse" aria-label="Draft stock entries">
        <thead>
          <tr className="border-b border-[var(--sd-line)]">
            <th className={head}>Date</th>
            <th className={head}>Type</th>
            <th className={head}>For</th>
            <th className={head}>Items</th>
            <th className={head}>Status</th>
            <th className={head}>Entry</th>
            <th className={head}>
              <span className="sr-only">Post</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {drafts.map((d) => (
            <tr key={d.name} className="border-t border-[var(--sd-line)]">
              <td className={cn(cell, "whitespace-nowrap")}>{dayLabel(d.posting_date)}</td>
              <td className={cn(cell, "font-medium text-[var(--sd-ink)]")}>{d.stock_entry_type}</td>
              <td className={cell}>
                {d.source?.animal ?? "—"}
                <div className="text-[11.5px] text-[var(--sd-quiet)]">{d.source?.name ?? "record no longer found"}</div>
              </td>
              <td className={cell}>
                {d.items.map((i, n) => (
                  <div key={n}>
                    {i.item_name || i.item_code} — {i.qty} {i.uom}
                  </div>
                ))}
              </td>
              <td className={cell}>
                <Status draft={d} />
                {d.short && <div className="mt-1 text-[11.5px] text-[var(--sd-amber)]">{d.short}</div>}
              </td>
              <td className={cn(cell, "whitespace-nowrap")}>
                <a
                  href={`/app/stock-entry/${encodeURIComponent(d.name)}`}
                  className="inline-flex items-center gap-1 text-[var(--sd-muted)] hover:text-[var(--sd-ink)]"
                >
                  {d.name} <ExternalLink className="h-3 w-3" />
                </a>
              </td>
              <td className={cn(cell, "text-right")}>
                <PostButton draft={d} busy={busy === d.name} onPost={onPost} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Transactions() {
  const [drafts, setDrafts] = useState<StockDraft[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    const r = await fetchStockDrafts();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setDrafts(r.drafts);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const post = useCallback(
    async (d: StockDraft) => {
      setBusy(d.name);
      const r = await postStockDraft(d.name);
      setBusy(null);
      if (isError(r)) {
        toast(r.error, "error");
      } else {
        toast(`${d.name} posted — the items have left the store.`, "ok");
      }
      void load();
    },
    [load, toast],
  );

  const ready = drafts?.filter((d) => d.can_post).length ?? 0;

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Stock" title="Transactions">
        <p className="max-w-2xl text-[14px] leading-relaxed text-[var(--sd-muted)]">
          Stock the farm&rsquo;s records used that the store could not cover on the day. Each record
          stands; its stock entry waits here as a draft until the items are in, and is posted from here.
        </p>
      </PageHeading>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>Draft stock entries</CardTitle>
            <CardDescription>
              {drafts === null
                ? "Loading…"
                : drafts.length
                  ? `${drafts.length} waiting · ${ready} ready to post`
                  : "Nothing is waiting — every record's stock has been posted."}
            </CardDescription>
          </div>
          <RefreshButton onClick={() => void load()} loading={loading} label="the drafts" />
        </CardHeader>
        <CardContent>
          {failure ? (
            <Notice tone="error">{failure}</Notice>
          ) : drafts === null ? null : (
            <Tabs defaultValue="calendar" className="flex flex-col gap-4">
              <TabsList className="self-start">
                <TabsTrigger value="calendar">
                  <CalendarDays className="mr-1.5 h-3.5 w-3.5" /> Calendar
                </TabsTrigger>
                <TabsTrigger value="list">
                  <List className="mr-1.5 h-3.5 w-3.5" /> List
                </TabsTrigger>
              </TabsList>
              <TabsContent value="calendar">
                <CalendarView drafts={drafts} busy={busy} onPost={post} />
              </TabsContent>
              <TabsContent value="list">
                {drafts.length ? (
                  <ListView drafts={drafts} busy={busy} onPost={post} />
                ) : (
                  <p className="text-[13px] text-[var(--sd-muted)]">Nothing is waiting.</p>
                )}
              </TabsContent>
            </Tabs>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
