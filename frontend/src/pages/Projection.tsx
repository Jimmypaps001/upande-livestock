import { useCallback, useEffect, useMemo, useState } from "react";
import { PackageSearch, TrendingDown } from "lucide-react";
import { RunOutChart, RUN_OUT_CHART_HEIGHT } from "@/components/feeding/RunOutChart";
import { ChartSkeleton, RowsSkeleton } from "@/components/Loading";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { RefreshButton } from "@/components/RefreshButton";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeaderRow,
  CardHeading,
  CardTitle,
  CardTools,
} from "@/components/ui/card";
import { isError } from "@/lib/frappe";
import {
  URGENCY_TONE,
  getFeedForecast,
  getFeedProjection,
  urgencyOf,
  urgencyWords,
  type FeedForecast,
  type FeedProjection,
  type ProjectedItem,
} from "@/lib/projection";
import { cn, fmt } from "@/lib/utils";

const HORIZONS = [14, 30, 60, 90];

/**
 * When the feed runs out.
 *
 * THE ANSWER IS A DATE. "3,200 kg of silage" tells nobody anything — eleven
 * days for this herd structure, three weeks for last month's. The farm buys
 * and cuts on a lead time, so the only number worth this much of a screen is
 * the day it runs out.
 *
 * The page states its own assumption rather than implying certainty: head
 * counts move, and a projection that modelled that would be a forecast of a
 * forecast. This one is arithmetic on today, which is something a person
 * standing in the store can check.
 */
export function ProjectionBody() {
  const [data, setData] = useState<FeedProjection | null>(null);
  const [ahead, setAhead] = useState<FeedForecast | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [flat, forward] = await Promise.all([
      getFeedProjection(days),
      getFeedForecast(days),
    ]);
    setLoading(false);
    if (isError(flat)) {
      setFailure(flat.error);
      return;
    }
    setFailure(null);
    setData(flat);
    setAhead(isError(forward) ? null : forward);
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const items = data?.items ?? [];
  const soon = useMemo(() => items.filter((i) => urgencyOf(i) !== "fine"), [items]);
  const gone = items.filter((i) => urgencyOf(i) === "gone");
  const next = items.find((i) => i.days_cover !== null && i.days_cover > 0);

  return (
    <>
      {failure && <Notice tone="error">{failure}</Notice>}

      <FigureRow>
        <Figure loading={!data} label="Feeds drawn" value={String(items.length)} hint="across every herd" />
        <Figure loading={!data} label="Already out" value={String(gone.length)} hint="nothing on hand" />
        <Figure
          loading={!data} label="Running low"
          value={String(soon.length - gone.length)}
          hint="inside ten days"
        />
        {/* The number the flat view cannot give: what the draw BECOMES once the
            herds have moved. The difference is the whole argument for the
            forward view sitting beside the current one. */}
        <Figure
          loading={!ahead}
          label={`Draw in ${days} days`}
          value={ahead ? fmt(ahead.items.reduce((t, i) => t + i.per_day_at_horizon, 0)) : "—"}
          unit="kg"
          hint={
            ahead
              ? `${ahead.items.reduce((t, i) => t + i.drift, 0) >= 0 ? "+" : ""}${fmt(
                  ahead.items.reduce((t, i) => t + i.drift, 0),
                )} on today, as the herds move`
              : ""
          }
        />
        <Figure
          loading={!data} label="Next to go"
          value={next ? next.item_name : "—"}
          hint={next?.runs_out_on ? `on ${next.runs_out_on}` : ""}
        />
      </FigureRow>

      {!!gone.length && (
        <Notice tone="error">
          {gone.map((g) => g.item_name).join(", ")}
          {gone.length === 1 ? " is" : " are"} being drawn every day with nothing on hand.
          Either the stock is not on the system or the ration is asking for something the
          farm does not have.
        </Notice>
      )}

      {!!ahead?.events.length && (
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>What changes between now and then</CardTitle>
              <CardDescription>
                {ahead.basis}. Every one of these is a move the farm's own rules
                already know about — nothing here is a guess about a service that
                has not happened.
              </CardDescription>
            </CardHeading>
          </CardHeaderRow>
          <CardContent className="pt-0">
            <ul className="flex flex-col gap-0.5">
              {ahead.events.slice(0, 12).map((e) => (
                <li
                  key={e.on}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 border-t border-[var(--sd-line)] px-1 py-2 text-[12.5px] first:border-t-0"
                >
                  <span className="text-[var(--sd-muted)]">
                    {e.what
                      .map((w) =>
                        w.kind === "birth"
                          ? `${w.heads === 0.5 ? "a calf" : `${w.heads} calves`} into ${w.to_herd}`
                          : `${w.heads} from ${w.from_herd} to ${w.to_herd}`,
                      )
                      .join(", ")}
                  </span>
                  <span className="tabular-nums text-[var(--sd-quiet)]">{e.on}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Stock falling away</CardTitle>
            <CardDescription>
              Each feed as a share of what is on hand today, so the fast ones are visible
              beside the big ones. Assumes {data?.basis ?? "today's herds and rations"}.
            </CardDescription>
          </CardHeading>
          <CardTools>
            <div className="flex items-center gap-1 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] p-0.5">
              {HORIZONS.map((h) => (
                <button
                  key={h}
                  type="button"
                  onClick={() => setDays(h)}
                  className={cn(
                    "rounded-[var(--sd-radius-pill)] px-2.5 py-1 text-[11.5px] font-medium transition-all",
                    h === days
                      ? "bg-[var(--sd-card)] text-[var(--sd-ink)] shadow-[var(--sd-shadow-1)]"
                      : "text-[var(--sd-muted)] hover:text-[var(--sd-ink)]",
                  )}
                >
                  {h}d
                </button>
              ))}
            </div>
            <RefreshButton onClick={load} loading={loading} label="the projection" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="pt-0">
          {data ? (
            <RunOutChart items={items} dates={data.dates} />
          ) : (
            <ChartSkeleton height={RUN_OUT_CHART_HEIGHT} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Every feed, soonest first</CardTitle>
            <CardDescription>
              Open one to see which herds draw it, and what it is mixed into.
            </CardDescription>
          </CardHeading>
        </CardHeaderRow>
        <CardContent className="pt-0">
          {!data ? (
            <RowsSkeleton rows={6} />
          ) : !items.length ? (
            <p className="text-[13px] text-[var(--sd-muted)]">
              No herd on the farm has a ration, so nothing is being drawn.
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {items.map((item) => (
                <ItemRow
                  key={item.item_code}
                  item={item}
                  open={open === item.item_code}
                  onToggle={() =>
                    setOpen(open === item.item_code ? null : item.item_code)
                  }
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </>
  );
}

function ItemRow({
  item,
  open,
  onToggle,
}: {
  item: ProjectedItem;
  open: boolean;
  onToggle: () => void;
}) {
  const tone = URGENCY_TONE[urgencyOf(item)];
  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all hover:bg-[var(--sd-bg-soft)]"
      >
        <span
          className="h-8 w-1 shrink-0 rounded-full"
          style={{ background: tone }}
          aria-hidden
        />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
            {item.item_name}
          </span>
          <span className="text-[11.5px] tabular-nums text-[var(--sd-muted)]">
            {fmt(item.on_hand)} {item.uom} on hand · {fmt(item.per_day)} a day
          </span>
        </span>
        <span className="shrink-0 text-right">
          <span className="block text-[12.5px] font-medium" style={{ color: tone }}>
            {urgencyWords(item)}
          </span>
          <span className="block text-[11px] tabular-nums text-[var(--sd-quiet)]">
            {item.runs_out_on || "—"}
          </span>
        </span>
      </button>

      {open && (
        <div className="mb-1 ml-4 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3.5 shadow-[var(--sd-shadow-inset)]">
          {!!item.herds.length && (
            <>
              <p className="mb-1.5 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
                <TrendingDown className="h-3.5 w-3.5" strokeWidth={2} />
                Fed straight to
              </p>
              <ul className="mb-3 flex flex-col gap-0.5">
                {item.herds.map((h) => (
                  <li
                    key={`${h.herd}-${h.per_head}`}
                    className="flex justify-between gap-4 text-[12px] text-[var(--sd-muted)]"
                  >
                    <span className="truncate">{h.herd}</span>
                    <span className="shrink-0 tabular-nums">
                      {h.heads} head × {fmt(h.per_head)} = {fmt(h.per_day)} {item.uom}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {!!item.concentrates.length && (
            <>
              <p className="mb-1.5 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
                <PackageSearch className="h-3.5 w-3.5" strokeWidth={2} />
                Mixed into
              </p>
              <ul className="flex flex-col gap-0.5">
                {item.concentrates.map((c, i) => (
                  <li
                    key={`${c.concentrate}-${i}`}
                    className="flex justify-between gap-4 text-[12px] text-[var(--sd-muted)]"
                  >
                    <span className="truncate">{c.concentrate}</span>
                    <span className="shrink-0 tabular-nums">
                      {fmt(c.per_day)} {item.uom} a day
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {!item.herds.length && !item.concentrates.length && (
            <p className="text-[12px] text-[var(--sd-muted)]">
              Nothing on the farm draws this today.
            </p>
          )}
        </div>
      )}
    </li>
  );
}
