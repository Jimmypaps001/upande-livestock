import { useCallback, useEffect, useState } from "react";
import { ProjectionBody } from "@/pages/Projection";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
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
import { formatWeight, getBeefDashboard, type BeefDashboard } from "@/lib/performance";

/**
 * The farm at a glance.
 *
 * Above, the beef figures: head count, average weight and average daily gain
 * for each herd, then what needs doing (weighings late, animals due to change
 * band, animals ready to leave). Below, the feed projection — what it will take
 * to keep the herds fed.
 */
export function Dashboard() {
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Dashboard" title="Dashboard">
        How the herds stand, and what it will take to keep them fed.
      </PageHeading>

      <BeefTiles />

      <ProjectionBody />
    </Page>
  );
}

function BeefTiles() {
  const [beef, setBeef] = useState<BeefDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getBeefDashboard();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setBeef(r.beef || null);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const waiting = loading && !beef;
  const herds = beef?.herds || [];
  const dash = (n: number | undefined) => (beef ? String(n ?? 0) : "—");

  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Beef herds</CardTitle>
          <CardDescription>
            Head, average weight and average daily gain for each herd, and the work the
            weights are asking for.
          </CardDescription>
        </CardHeading>
        <CardTools>
          <RefreshButton onClick={load} loading={loading} label="the beef figures" />
        </CardTools>
      </CardHeaderRow>
      <CardContent className="flex flex-col gap-4">
        {failure && <Notice tone="error">{failure}</Notice>}

        <FigureRow>
          <Figure
            label="Weighings overdue"
            value={dash(beef?.weighings_overdue)}
            hint="past the monthly interval and grace"
            loading={waiting}
          />
          <Figure
            label="Band moves due"
            value={dash(beef?.band_moves_due)}
            hint="outside their herd's weight band"
            loading={waiting}
          />
          <Figure
            label="Ready for exit"
            value={dash(beef?.ready_for_exit)}
            hint="above the top band"
            loading={waiting}
          />
        </FigureRow>

        {!waiting && beef && herds.length === 0 && (
          <p className="text-[13px] text-[var(--sd-muted)]">
            No fattening, breeding or calf herds yet. Set a herd's class on the Herds
            page.
          </p>
        )}

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {waiting &&
            [0, 1, 2].map((i) => (
              <div key={i} className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] p-1">
                <Figure label="Herd" value="—" loading />
              </div>
            ))}
          {herds.map((h) => (
            <div
              key={h.herd}
              className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-1 py-1 shadow-[var(--sd-shadow-inset)]"
            >
              <p className="px-5 pt-3 text-[13px] font-medium text-[var(--sd-ink)]">
                {h.herd}
                <span className="ml-2 text-[11px] font-normal text-[var(--sd-quiet)]">
                  {h.herd_class}
                </span>
              </p>
              <div className="grid grid-cols-3">
                <Figure label="Head" value={String(h.head_count)} />
                <Figure label="Avg weight" value={formatWeight(h.avg_weight_kg)} />
                <Figure
                  label="Avg gain"
                  value={h.avg_adg_kg === null ? "—" : h.avg_adg_kg.toFixed(2)}
                  unit="kg/d"
                />
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
