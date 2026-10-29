import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Figure, FigureRow } from "@/components/Figure";
import { Mark, Notice } from "@/components/feeding/Notice";
import { HEADER_PILL } from "@/components/header-controls";
import { RowsSkeleton } from "@/components/Loading";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { ShoatRecordDialog, type RecordKind } from "@/components/shoats/ShoatRecordDialog";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isError } from "@/lib/frappe";
import {
  CLASS_KEYS,
  countsText,
  formatChange,
  formatLiveWeight,
  getShoatHerd,
  getShoatOptions,
  listShoatHerds,
  varianceNote,
  type HerdReply,
  type HerdsReply,
  type Options,
  type ShoatHerd,
  type Species,
} from "@/lib/shoats";
import { cn } from "@/lib/utils";

const TH = "px-3 py-2.5 font-medium";
const HEAD_ROW = "border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]";
const BOX = "overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]";
const EMPTY = "px-1 py-6 text-center text-[13px] text-[var(--sd-muted)]";

/**
 * Shoats: the sheep flocks and goat herds, kept by number.
 *
 * A herd's head is the replay of its ledger (counts, births, deaths, sales,
 * transfers), so every figure here is read, never typed. The detail below the
 * list answers the four things a manager asks of a flock: what happened (the
 * ledger, with each head count's variance), how heavy it is (weight samples),
 * what is due (matings with expected lambing or kidding) and what it was given
 * (treatments, with the withdrawal still running).
 */
export function Shoats() {
  const [list, setList] = useState<HerdsReply | null>(null);
  const [species, setSpecies] = useState<"All" | Species>("All");
  const [herd, setHerd] = useState("");
  const [detail, setDetail] = useState<HerdReply | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [recording, setRecording] = useState<RecordKind | null>(null);
  const toast = useToast();

  const latest = useRef(0);
  const load = useCallback(async () => {
    const mine = ++latest.current;
    setLoading(true);
    const r = await listShoatHerds();
    if (mine !== latest.current) return;
    if (isError(r)) {
      setFailure(r.error);
      setLoading(false);
      return;
    }
    setFailure(null);
    const reply = r as HerdsReply;
    setList(reply);
    setHerd((h) => h || reply.herds[0]?.name || "");
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
    void getShoatOptions().then((o) => !isError(o) && setOptions(o as Options));
  }, [load]);

  const loadDetail = useCallback(async () => {
    if (!herd) return;
    const r = await getShoatHerd(herd);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setDetail(r as HerdReply);
  }, [herd]);

  useEffect(() => {
    setDetail(null);
    void loadDetail();
  }, [loadDetail]);

  const rows = useMemo(
    () => (list?.herds || []).filter((h) => species === "All" || h.species === species),
    [list, species],
  );
  const totals = list?.totals;
  const showing = detail && detail.herd.name === herd ? detail : null;
  const refresh = () => {
    void load();
    void loadDetail();
  };

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Shoats" title="Shoats">
        Sheep and goats are kept by number, herd by herd. The head, by ewes or does, rams or bucks, lambs or kids,
        is whatever the ledger of counts and movements says.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Herds</CardTitle>
            <CardDescription>Choose a herd to see its ledger, weights, breeding and treatments.</CardDescription>
          </CardHeading>
          <CardTools>
            <Select value={species} onValueChange={(v) => setSpecies(v as "All" | Species)}>
              <SelectTrigger id="shoat-species" aria-label="Species" className={HEADER_PILL}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="All">Sheep and goats</SelectItem>
                <SelectItem value="Sheep">Sheep</SelectItem>
                <SelectItem value="Goat">Goats</SelectItem>
              </SelectContent>
            </Select>
            <RefreshButton onClick={refresh} loading={loading} label="the herds" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-col gap-3">
          <FigureRow>
            <Figure label="Sheep" value={totals ? String(totals.Sheep.head) : "—"} unit="head"
              hint={totals ? `${totals.Sheep.herds} flocks` : undefined} loading={loading && !list} />
            <Figure label="Goats" value={totals ? String(totals.Goat.head) : "—"} unit="head"
              hint={totals ? `${totals.Goat.herds} herds` : undefined} loading={loading && !list} />
            <Figure label="Shoats" value={totals ? String(totals.Shoats.head) : "—"} unit="head" loading={loading && !list} />
            <Figure label="Live weight"
              value={totals && totals.Shoats.live_weight_kg ? Math.round(totals.Shoats.live_weight_kg).toLocaleString() : "—"}
              unit="kg" hint="from the latest samples" loading={loading && !list} />
          </FigureRow>

          {loading && !list ? (
            <RowsSkeleton rows={4} />
          ) : rows.length === 0 ? (
            <p className={EMPTY}>{failure ? "The herds could not be loaded." : "No shoat herds yet."}</p>
          ) : (
            <div className={BOX}>
              <table className="w-full min-w-[56rem] text-[13px]">
                <thead>
                  <tr className={HEAD_ROW}>
                    <th className={TH}>Herd</th>
                    <th className={cn(TH, "text-right")}>Ewes / Does</th>
                    <th className={cn(TH, "text-right")}>Rams / Bucks</th>
                    <th className={cn(TH, "text-right")}>Lambs / Kids</th>
                    <th className={cn(TH, "text-right")}>Others</th>
                    <th className={cn(TH, "text-right")}>Head</th>
                    <th className={cn(TH, "text-right")}>Live weight</th>
                    <th className={TH}>Last count</th>
                    <th className={TH}>Due</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((h) => (
                    <HerdRow key={h.name} h={h} selected={h.name === herd} onSelect={() => setHerd(h.name)} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {herd && (
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>{showing?.herd.label || herd}</CardTitle>
              <CardDescription>
                {showing
                  ? [showing.herd.species, showing.herd.breed, showing.herd.paddock].filter(Boolean).join(" · ")
                  : "Loading…"}
              </CardDescription>
            </CardHeading>
            <CardTools>
              <Button size="sm" variant="outline" className="rounded-full" disabled={!showing}
                onClick={() => setRecording("event")}>
                Record count or movement
              </Button>
              <Button size="sm" variant="outline" className="rounded-full" disabled={!showing}
                onClick={() => setRecording("weight")}>
                Weigh a sample
              </Button>
              <Button size="sm" variant="outline" className="rounded-full" disabled={!showing}
                onClick={() => setRecording("treatment")}>
                Record treatment
              </Button>
            </CardTools>
          </CardHeaderRow>
          <CardContent className="flex flex-col gap-4">
            {showing ? <Detail d={showing} /> : <RowsSkeleton rows={4} />}
          </CardContent>
        </Card>
      )}

      {recording && showing && (
        <ShoatRecordDialog
          kind={recording}
          herd={showing.herd}
          options={options}
          otherHerds={(list?.herds || [])
            .filter((h) => h.name !== showing.herd.name && h.species === showing.herd.species)
            .map((h) => ({ name: h.name, label: h.label }))}
          open
          onOpenChange={(o) => !o && setRecording(null)}
          onDone={(m) => {
            toast(m);
            refresh();
          }}
        />
      )}
    </Page>
  );
}

function HerdRow({ h, selected, onSelect }: { h: ShoatHerd; selected: boolean; onSelect: () => void }) {
  return (
    <tr
      data-selected={selected ? "true" : undefined}
      className={cn("border-b border-[var(--sd-line-soft)] last:border-0", selected && "bg-[var(--sd-bg-soft)]")}
    >
      <td className="px-3 py-2.5">
        <button type="button" onClick={onSelect} aria-label={`Open ${h.label}`}
          className="text-left font-medium text-[var(--sd-ink)] hover:underline">
          {h.label}
        </button>
        <div className="text-[11px] text-[var(--sd-quiet)]">
          {h.species}
          {h.breed ? ` · ${h.breed}` : ""}
        </div>
        {h.in_withdrawal && (
          <div className="mt-0.5">
            <Mark>Withdrawal to {h.withdrawal_until}</Mark>
          </div>
        )}
      </td>
      {CLASS_KEYS.map((k) => (
        <td key={k} className="px-3 py-2.5 text-right tabular-nums">{h.head[k]}</td>
      ))}
      <td className="px-3 py-2.5 text-right font-medium tabular-nums text-[var(--sd-ink)]">{h.head.total}</td>
      <td className="px-3 py-2.5 text-right tabular-nums">
        {formatLiveWeight(h)}
        {h.avg_weight_kg !== null && h.weight_basis !== "none" && (
          <div className="text-[11px] text-[var(--sd-quiet)]">{h.avg_weight_kg} kg avg</div>
        )}
      </td>
      <td className="px-3 py-2.5 text-[var(--sd-muted)]">{h.last_count_date || "—"}</td>
      <td className="px-3 py-2.5 text-[var(--sd-muted)]">
        {h.next_due ? (
          <>
            {h.next_due.expected_birth_date}
            <div className={cn("text-[11px]", h.mating_status !== "Pending" && "font-medium text-[var(--sd-amber)]")}>
              {h.mating_status === "Pending" ? `in ${h.next_due.days_to_due} d` : h.mating_status}
            </div>
          </>
        ) : (
          "—"
        )}
      </td>
    </tr>
  );
}

function Detail({ d }: { d: HerdReply }) {
  const h = d.herd;
  return (
    <>
      <FigureRow>
        {CLASS_KEYS.map((k) => (
          <Figure key={k} label={h.labels[k]} value={String(h.head[k])} />
        ))}
        <Figure label="Head" value={String(h.head.total)} />
        <Figure label="Live weight" value={h.weight_basis === "none" ? "—" : Math.round(h.live_weight_kg).toLocaleString()}
          unit="kg" hint={h.weight_basis === "none" ? "no sample yet" : `${h.weight_basis}, ${h.weight_date}`} />
      </FigureRow>
      {h.in_withdrawal && (
        <Notice tone="info">Drug withdrawal runs until {h.withdrawal_until}: the meat is not safe before then.</Notice>
      )}
      <Tabs defaultValue="ledger">
        <TabsList>
          <TabsTrigger value="ledger">Ledger</TabsTrigger>
          <TabsTrigger value="weights">Weights</TabsTrigger>
          <TabsTrigger value="breeding">Breeding</TabsTrigger>
          <TabsTrigger value="treatments">Treatments</TabsTrigger>
        </TabsList>

        <TabsContent value="ledger" className="mt-3">
          {d.ledger.length === 0 ? (
            <p className={EMPTY}>Nothing has been recorded for this herd.</p>
          ) : (
            <div className={BOX}>
              <table className="w-full min-w-[44rem] text-[13px]">
                <thead>
                  <tr className={HEAD_ROW}>
                    <th className={TH}>Date</th>
                    <th className={TH}>Event</th>
                    <th className={TH}>Animals</th>
                    <th className={cn(TH, "text-right")}>Change</th>
                    <th className={cn(TH, "text-right")}>Head after</th>
                    <th className={TH}>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {d.ledger.map((e) => {
                    const variance = varianceNote(e, h.labels);
                    return (
                      <tr key={e.name} className="border-b border-[var(--sd-line-soft)] last:border-0">
                        <td className="px-3 py-2.5 tabular-nums">{e.event_date}</td>
                        <td className="px-3 py-2.5 font-medium text-[var(--sd-ink)]">{e.event_type}</td>
                        <td className="px-3 py-2.5">{countsText(e, h.labels)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatChange(e.change)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{e.head_after}</td>
                        <td className="px-3 py-2.5 text-[var(--sd-muted)]">
                          {e.event_type === "Head Count" &&
                            (variance ? (
                              <span className="font-medium text-[var(--sd-amber)]">Variance {variance}</span>
                            ) : (
                              "Agreed with the ledger"
                            ))}
                          {e.cause && <span>{e.cause}</span>}
                          {e.other_herd && <span>{e.event_type === "Transfer In" ? "from" : "to"} {e.other_herd}</span>}
                          {e.reason && !e.cause && !e.other_herd && e.event_type !== "Head Count" && <span>{e.reason}</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="weights" className="mt-3">
          {d.weights.length === 0 ? (
            <p className={EMPTY}>No animals have been weighed yet.</p>
          ) : (
            <div className={BOX}>
              <table className="w-full min-w-[36rem] text-[13px]">
                <thead>
                  <tr className={HEAD_ROW}>
                    <th className={TH}>Date</th>
                    <th className={TH}>Class</th>
                    <th className={cn(TH, "text-right")}>Weighed</th>
                    <th className={cn(TH, "text-right")}>Average</th>
                    <th className={cn(TH, "text-right")}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {d.weights.map((w) => (
                    <tr key={w.name} className="border-b border-[var(--sd-line-soft)] last:border-0">
                      <td className="px-3 py-2.5 tabular-nums">{w.sample_date}</td>
                      <td className="px-3 py-2.5">
                        {w.sample_class === "All" ? "Whole herd" : h.labels[w.sample_class as keyof typeof h.labels]}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{w.animals_weighed}</td>
                      <td className="px-3 py-2.5 text-right font-medium tabular-nums text-[var(--sd-ink)]">{w.average_kg} kg</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{w.total_kg} kg</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="breeding" className="mt-3">
          {d.matings.length === 0 ? (
            <p className={EMPTY}>No matings recorded.</p>
          ) : (
            <div className={BOX}>
              <table className="w-full min-w-[44rem] text-[13px]">
                <thead>
                  <tr className={HEAD_ROW}>
                    <th className={TH}>Mating</th>
                    <th className={cn(TH, "text-right")}>{h.labels.females} put to</th>
                    <th className={cn(TH, "text-right")}>{h.labels.males} in</th>
                    <th className={TH}>Expected</th>
                    <th className={TH}>Status</th>
                    <th className={cn(TH, "text-right")}>Born alive</th>
                    <th className={cn(TH, "text-right")}>Born dead</th>
                  </tr>
                </thead>
                <tbody>
                  {d.matings.map((m) => (
                    <tr key={m.name} className="border-b border-[var(--sd-line-soft)] last:border-0">
                      <td className="px-3 py-2.5 tabular-nums">{m.mating_start} to {m.mating_end}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{m.females_served}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{m.males_in}</td>
                      <td className="px-3 py-2.5 tabular-nums">{m.expected_birth_date}</td>
                      <td className={cn("px-3 py-2.5", m.status === "Due" || m.status === "Overdue" ? "font-medium text-[var(--sd-amber)]" : "")}>
                        {m.status}
                        {m.birth_rate_pct !== null && (
                          <div className="text-[11px] text-[var(--sd-quiet)]">{m.birth_rate_pct}% born per female</div>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{m.born_alive}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{m.born_dead}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="treatments" className="mt-3">
          {d.treatments.length === 0 ? (
            <p className={EMPTY}>No treatments recorded.</p>
          ) : (
            <div className={BOX}>
              <table className="w-full min-w-[44rem] text-[13px]">
                <thead>
                  <tr className={HEAD_ROW}>
                    <th className={TH}>Date</th>
                    <th className={TH}>Type</th>
                    <th className={TH}>Product</th>
                    <th className={cn(TH, "text-right")}>Treated</th>
                    <th className={cn(TH, "text-right")}>Issued</th>
                    <th className={TH}>Withdrawal ends</th>
                  </tr>
                </thead>
                <tbody>
                  {d.treatments.map((t) => (
                    <tr key={t.name} className="border-b border-[var(--sd-line-soft)] last:border-0">
                      <td className="px-3 py-2.5 tabular-nums">{t.treatment_date}</td>
                      <td className="px-3 py-2.5 font-medium text-[var(--sd-ink)]">{t.treatment_type}</td>
                      <td className="px-3 py-2.5">
                        {t.product_name || t.product}
                        {t.diagnosis && <div className="text-[11px] text-[var(--sd-quiet)]">{t.diagnosis}</div>}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{t.number_treated}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{t.quantity} {t.dose_uom}</td>
                      <td className="px-3 py-2.5 tabular-nums text-[var(--sd-muted)]">{t.withdrawal_end || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </>
  );
}
