import { useCallback, useEffect, useRef, useState } from "react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { HEADER_PILL } from "@/components/header-controls";
import { RowsSkeleton } from "@/components/Loading";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { STICKY_HEAD, ScrollTable } from "@/components/ScrollTable";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeaderRow,
  CardHeading,
  CardTitle,
  CardTools,
} from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  fmtMoney,
  fmtPerAnimal,
  getCostPerAnimal,
  HISTORY_LABEL,
  historyDaysLabel,
  monthLabel,
  monthWindow,
  recentMonths,
  type CostReport,
} from "@/lib/costing";
import { isError } from "@/lib/frappe";
import { routeHash } from "@/lib/router";
import { todayISO } from "@/lib/utils";

const TH = "px-3 py-2.5 font-medium";
const THR = `${TH} text-right`;
const TD = "px-3 py-2.5 tabular-nums";
const TDR = `${TD} text-right`;
const HEAD_ROW =
  "border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]";
const BODY_ROW = "border-b border-[var(--sd-line-soft)] last:border-0";
const FRAME = "rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]";
const HISTORY_TAG = "block text-[11px] font-normal text-[var(--sd-quiet)]";

/**
 * Costs: what keeping an animal costs, day by day.
 *
 * Feed, medicine, labour and fuel for each day over every animal on the farm
 * that day — the farm spreadsheet's "Daily Totals", read from the stock ledger
 * instead of typed. Below it, each herd's feed per head (feed is the one cost
 * that knows its herd), and, where upande_production is installed, the
 * machines that worked for the feedlot and what silage cost per kg.
 */
export function Costs() {
  const today = todayISO();
  const months = recentMonths(today, 12);
  const [month, setMonth] = useState(months[0]);
  const [data, setData] = useState<CostReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);

  const latest = useRef(0);
  const load = useCallback(async () => {
    const mine = ++latest.current;
    const { from, to } = monthWindow(month, today);
    setLoading(true);
    const r = await getCostPerAnimal(from, to);
    if (mine !== latest.current) return;
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    // Lists default to empty so a thin answer draws an empty table, not a crash.
    const got = r as Partial<CostReport>;
    setData({
      ...(got as CostReport),
      days: got.days || [],
      months: got.months || [],
      herds: got.herds || [],
      machines: got.machines || [],
    });
  }, [month, today]);

  useEffect(() => {
    void load();
  }, [load]);

  const total = data?.total;
  const waiting = loading && !data;

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Costs" title="Cost per animal">
        Feed, medicine, labour and fuel for each day, spread over every animal on the farm that
        day. Feed is also shown per herd, since every feed issue names the herd that ate it.
      </PageHeading>
      {failure && <Notice tone="error">{failure}</Notice>}

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>{monthLabel(month)}</CardTitle>
            <CardDescription>
              Costed from the stock ledger. Labour is what was entered on{" "}
              <a className="underline" href={routeHash("labour")}>
                Daily Labour
              </a>
              .
            </CardDescription>
          </CardHeading>
          <CardTools>
            <Select value={month} onValueChange={setMonth}>
              <SelectTrigger aria-label="Month" className={HEADER_PILL}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {months.map((m) => (
                  <SelectItem key={m} value={m}>
                    {monthLabel(m)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <RefreshButton onClick={load} loading={loading} label="the costs" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-4">
          <FigureRow>
            <Figure
              label="Per animal per day"
              value={fmtPerAnimal(total?.cost_per_animal)}
              unit="KES"
              hint="the month's cost over its animal-days"
              loading={waiting}
            />
            <Figure label="Month total" value={fmtMoney(total?.total_cost)} unit="KES" loading={waiting} />
            <Figure
              label="Animals, on average"
              value={total && total.days ? (total.animal_days / total.days).toFixed(0) : "—"}
              hint="individual animals and shoats by number"
              loading={waiting}
            />
          </FigureRow>
          <FigureRow>
            <Figure label="Feed" value={fmtMoney(total?.feed_cost)} unit="KES" loading={waiting} />
            <Figure label="Medicine" value={fmtMoney(total?.medicine_cost)} unit="KES" loading={waiting} />
            <Figure label="Labour" value={fmtMoney(total?.labour_cost)} unit="KES" loading={waiting} />
            <Figure
              label="Fuel"
              value={data && !data.fuel_available ? "—" : fmtMoney(total?.fuel_cost)}
              unit="KES"
              hint={data && !data.fuel_available ? "not available" : undefined}
              loading={waiting}
            />
          </FigureRow>
          {!!total?.history_feed_cost && (
            <Notice tone="info">
              KES {fmtMoney(total.history_feed_cost)} of this month's feed is {HISTORY_LABEL}: days the
              herds were fed before the app, never issued from the stores. Those days are marked.
            </Notice>
          )}
          {data && !data.fuel_available && data.production_installed && data.fuel_note && (
            <Notice tone="info">Fuel is not counted: {data.fuel_note}</Notice>
          )}
          <DayTable data={data} loading={loading} />
        </CardContent>
      </Card>

      <HerdCard data={data} loading={loading} />
      {data?.production_installed && <MachinesCard data={data} />}
      {data?.production_installed && <SilageCard data={data} />}
    </Page>
  );
}

function DayTable({ data, loading }: { data: CostReport | null; loading: boolean }) {
  if (!data) return loading ? <RowsSkeleton rows={8} /> : null;
  const fuelShown = data.fuel_available;
  return (
    <ScrollTable tall className={FRAME}>
      <table className="w-full min-w-[46rem] text-[13px]" data-testid="cost-days">
        <thead className={STICKY_HEAD}>
          <tr className={HEAD_ROW}>
            <th className={TH}>Day</th>
            <th className={THR}>Feed</th>
            <th className={THR}>Medicine</th>
            <th className={THR}>Labour</th>
            <th className={THR}>Fuel</th>
            <th className={THR}>Total</th>
            <th className={THR}>Animals</th>
            <th className={THR}>Per animal</th>
          </tr>
        </thead>
        <tbody>
          {data.days.map((d) => (
            <tr key={d.date} className={BODY_ROW}>
              <td className={TD}>{d.date}</td>
              <td className={TDR}>
                {fmtMoney(d.feed_cost)}
                {d.feed_from_history && (
                  <span className={HISTORY_TAG} data-cell="feed-history">
                    {HISTORY_LABEL}
                  </span>
                )}
              </td>
              <td className={TDR}>{fmtMoney(d.medicine_cost)}</td>
              <td className={TDR}>{fmtMoney(d.labour_cost)}</td>
              <td className={TDR}>{fuelShown ? fmtMoney(d.fuel_cost) : "—"}</td>
              <td className={`${TDR} font-medium`}>{fmtMoney(d.total_cost)}</td>
              <td className={TDR}>{d.animals}</td>
              <td className={`${TDR} font-medium`} data-cell="per-animal">
                {fmtPerAnimal(d.cost_per_animal)}
              </td>
            </tr>
          ))}
        </tbody>
        {data.months.length > 0 && (
          <tfoot>
            {data.months.map((m) => (
              <tr key={m.month} className="border-t border-[var(--sd-line)] font-medium">
                <td className={TD}>{monthLabel(m.month)}</td>
                <td className={TDR}>{fmtMoney(m.feed_cost)}</td>
                <td className={TDR}>{fmtMoney(m.medicine_cost)}</td>
                <td className={TDR}>{fmtMoney(m.labour_cost)}</td>
                <td className={TDR}>{fuelShown ? fmtMoney(m.fuel_cost) : "—"}</td>
                <td className={TDR}>{fmtMoney(m.total_cost)}</td>
                <td className={TDR}>{m.average_animals}</td>
                <td className={TDR} data-cell="month-per-animal">
                  {fmtPerAnimal(m.cost_per_animal)}
                </td>
              </tr>
            ))}
          </tfoot>
        )}
      </table>
    </ScrollTable>
  );
}

function HerdCard({ data, loading }: { data: CostReport | null; loading: boolean }) {
  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Feed per head</CardTitle>
          <CardDescription>
            What each herd's feed cost per head per day: the feed issued to it over the head-days it
            carried. A day {HISTORY_LABEL} counts the tracker's cost over the head the tracker fed.
          </CardDescription>
        </CardHeading>
      </CardHeaderRow>
      <CardContent>
        {!data ? (
          loading ? <RowsSkeleton rows={4} /> : null
        ) : data.herds.length === 0 ? (
          <p className="text-[13px] text-[var(--sd-muted)]">No feed was issued to a herd this month.</p>
        ) : (
          <div className={`overflow-x-auto ${FRAME}`}>
            <table className="w-full min-w-[34rem] text-[13px]" data-testid="cost-herds">
              <thead>
                <tr className={HEAD_ROW}>
                  <th className={TH}>Herd</th>
                  <th className={THR}>Feed</th>
                  <th className={THR}>Head, on average</th>
                  <th className={THR}>Per head per day</th>
                </tr>
              </thead>
              <tbody>
                {data.herds.map((h) => (
                  <tr key={h.herd} className={BODY_ROW}>
                    <td className="px-3 py-2.5">
                      {h.herd}
                      {!!h.history_days && (
                        <span className={HISTORY_TAG} data-cell="herd-history">
                          {historyDaysLabel(h.history_days)}
                        </span>
                      )}
                    </td>
                    <td className={TDR}>{fmtMoney(h.feed_cost)}</td>
                    <td className={TDR}>{h.average_heads}</td>
                    <td className={`${TDR} font-medium`}>{fmtPerAnimal(h.feed_cost_per_head_day)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MachinesCard({ data }: { data: CostReport }) {
  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Machines that worked for the feedlot</CardTitle>
          <CardDescription>
            Allocations charged to the herds' cost centres in Production, with the diesel each burned.
          </CardDescription>
        </CardHeading>
      </CardHeaderRow>
      <CardContent>
        {!data.fuel_available ? (
          <p className="text-[13px] text-[var(--sd-muted)]">
            {data.fuel_note || "Machine work is not available."}
          </p>
        ) : data.machines.length === 0 ? (
          <p className="text-[13px] text-[var(--sd-muted)]">No machine worked for the feedlot this month.</p>
        ) : (
          <ScrollTable className={FRAME}>
            <table className="w-full min-w-[40rem] text-[13px]" data-testid="cost-machines">
              <thead className={STICKY_HEAD}>
                <tr className={HEAD_ROW}>
                  <th className={TH}>Machine</th>
                  <th className={TH}>Operator</th>
                  <th className={TH}>Started</th>
                  <th className={THR}>Hours</th>
                  <th className={THR}>Diesel (L)</th>
                  <th className={THR}>Diesel cost</th>
                </tr>
              </thead>
              <tbody>
                {data.machines.map((m, i) => (
                  <tr key={m.allocation || i} className={BODY_ROW}>
                    <td className="px-3 py-2.5">{m.machine || "—"}</td>
                    <td className="px-3 py-2.5">{m.operator_name || m.operator || "—"}</td>
                    <td className={TD}>{(m.start_time || "").slice(0, 16) || "—"}</td>
                    <td className={TDR}>{m.duration_hours.toFixed(1)}</td>
                    <td className={TDR}>{m.diesel_litres.toFixed(1)}</td>
                    <td className={TDR}>{fmtMoney(m.diesel_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollTable>
        )}
      </CardContent>
    </Card>
  );
}

function SilageCard({ data }: { data: CostReport }) {
  const silage = data.silage;
  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Silage cost per kg</CardTitle>
          <CardDescription>
            From Production's silage cycles: what each cycle cost over the kilograms it ensiled. This is
            the rate the silage enters the store at, and so what the herds' feed is costed with.
          </CardDescription>
        </CardHeading>
      </CardHeaderRow>
      <CardContent>
        {!silage || !silage.available ? (
          <p className="text-[13px] text-[var(--sd-muted)]">
            {silage?.reason || "Silage costs are not available."}
          </p>
        ) : silage.cycles.length === 0 ? (
          <p className="text-[13px] text-[var(--sd-muted)]">No silage cycle in this month.</p>
        ) : (
          <div className={`overflow-x-auto ${FRAME}`}>
            <table className="w-full min-w-[34rem] text-[13px]" data-testid="cost-silage">
              <thead>
                <tr className={HEAD_ROW}>
                  <th className={TH}>Cycle</th>
                  <th className={TH}>Crop</th>
                  <th className={THR}>Ensiled (kg)</th>
                  <th className={THR}>Cost</th>
                  <th className={THR}>Per kg</th>
                </tr>
              </thead>
              <tbody>
                {silage.cycles.map((c, i) => (
                  <tr key={c.cycle || i} className={BODY_ROW}>
                    <td className="px-3 py-2.5">{c.cycle || "—"}</td>
                    <td className="px-3 py-2.5">{c.crop || "—"}</td>
                    <td className={TDR}>{fmtMoney(c.ensiled_kg)}</td>
                    <td className={TDR}>{fmtMoney(c.total_cost)}</td>
                    <td className={`${TDR} font-medium`}>{fmtMoney(c.cost_per_kg, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
