import { useCallback, useEffect, useRef, useState } from "react";
import { Notice } from "@/components/feeding/Notice";
import { PaddockMap } from "@/components/paddocks/PaddockMap";
import { Figure, FigureRow } from "@/components/Figure";
import { RowsSkeleton } from "@/components/Loading";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Card, CardContent, CardHeaderRow, CardHeading, CardTitle, CardTools } from "@/components/ui/card";
import { isError } from "@/lib/frappe";
import { RESTING_COLOUR, getPaddockMap, perHerd, type PaddockMapData } from "@/lib/paddocks";
import { cn } from "@/lib/utils";

const TH = "px-3 py-2.5 font-medium";

/** Production · Paddock Map: where each herd stands, and whether the paddocks are enough to rotate. */
export function Paddocks() {
  const [data, setData] = useState<PaddockMapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const latest = useRef(0);

  const load = useCallback(async () => {
    const mine = ++latest.current;
    setLoading(true);
    const r = await getPaddockMap();
    if (mine !== latest.current) return;
    if (isError(r)) setFailure(r.error);
    else {
      setFailure(null);
      setData(r as PaddockMapData);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rot = data?.rotation;
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Beef" title="Paddock Map">
        Each paddock and feedlot pen, coloured by the herd standing on it with its head count. Paddocks with no
        herd are resting.
      </PageHeading>
      {failure && <Notice tone="error">{failure}</Notice>}
      {rot && (
        <div data-testid="rotation">
          <Notice tone={rot.enough ? "ok" : "error"}>{rot.message}</Notice>
        </div>
      )}
      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>Map</CardTitle>
          </CardHeading>
          <CardTools>
            <RefreshButton onClick={load} loading={loading} label="the map" />
          </CardTools>
        </CardHeaderRow>
        <CardContent>
          {!data ? (
            loading ? (
              <RowsSkeleton rows={8} />
            ) : (
              <p className="px-1 py-6 text-center text-[13px] text-[var(--sd-muted)]">The map could not be loaded.</p>
            )
          ) : (
            <div className="flex flex-col gap-3">
              {rot && (
                <FigureRow>
                  <Figure label="Paddocks" value={String(rot.paddocks)} hint={`${rot.grazing_ha} ha in all`} />
                  <Figure label="Grazing herds" value={String(rot.grazing_herds)} hint={`${rot.grazing_head} head`} />
                  <Figure label="Paddocks per herd" value={perHerd(rot)} hint={`${rot.needed_per_herd} needed to rotate`} />
                  <Figure label="Rest between grazings" value={rot.rest_days === null ? "—" : `${rot.rest_days}`} unit="days" hint={`${rot.target_rest_days} wanted`} />
                  <Figure label="Grazing density" value={rot.head_per_ha === null ? "—" : String(rot.head_per_ha)} unit="head/ha" />
                </FigureRow>
              )}
              <PaddockMap places={data.places} selected={selected} onSelect={setSelected} />
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-1" data-testid="paddock-legend">
                {data.herds
                  .filter((h) => h.colour)
                  .map((h) => (
                    <span key={h.herd} className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--sd-muted)]">
                      <span className="size-3 rounded-sm" style={{ background: h.colour ?? RESTING_COLOUR }} />
                      {h.herd} <span className="tabular-nums">{h.heads}</span>
                    </span>
                  ))}
                <span className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--sd-muted)]">
                  <span className="size-3 rounded-sm" style={{ background: RESTING_COLOUR }} />
                  Resting
                </span>
              </div>
              {data.unplaced.length > 0 && (
                <p className="px-1 text-[12.5px] text-[var(--sd-amber)]" data-testid="unplaced">
                  Not placed on a paddock or pen: {data.unplaced.join(", ")}.
                </p>
              )}
              <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
                <table className="w-full min-w-[40rem] text-[13px]" data-testid="paddock-rows">
                  <thead>
                    <tr className="border-b border-[var(--sd-line)] text-left text-[11px] uppercase tracking-[0.1em] text-[var(--sd-quiet)]">
                      <th className={TH}>Place</th>
                      <th className={TH}>Herd</th>
                      <th className={cn(TH, "text-right")}>Head</th>
                      <th className={cn(TH, "text-right")}>Area</th>
                      <th className={cn(TH, "text-right")}>Head per ha</th>
                      <th className={cn(TH, "text-right")}>Feed on hand</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.places.map((p) => (
                      <tr
                        key={p.warehouse}
                        className={cn("cursor-pointer border-b border-[var(--sd-line-soft)] last:border-0", selected === p.warehouse && "bg-[var(--sd-bg-soft)]")}
                        onClick={() => setSelected(p.warehouse)}
                      >
                        <td className="px-3 py-2.5 font-medium text-[var(--sd-ink)]">
                          <span className="mr-2 inline-block size-2.5 rounded-sm align-middle" style={{ background: p.colour }} />
                          {p.label} <span className="font-normal text-[var(--sd-quiet)]">{p.kind === "Pen" ? "pen" : ""}</span>
                        </td>
                        <td className="px-3 py-2.5 text-[var(--sd-muted)]">{p.herds.length ? p.herds.map((h) => h.herd).join(", ") : "Resting"}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{p.heads || "—"}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{p.area_ha === null ? "—" : `${p.area_ha} ha`}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{p.head_per_ha ?? "—"}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{p.feed_kg ? `${Math.round(p.feed_kg).toLocaleString("en-US")} kg` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="px-1 text-[11.5px] text-[var(--sd-quiet)]">
                Paddocks are warehouses of type Paddock and pens of type Pen, each with its outline as GeoJSON. A herd's paddock is set on the herd; its mixed feed is moved there after it is made.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
