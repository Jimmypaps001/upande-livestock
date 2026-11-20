import { useCallback, useEffect, useState } from "react";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { QualityBatch } from "@/components/quality/QualityBatch";
import { QualityTrendCard } from "@/components/milking/MilkCharts";
import { Page, PageHeading } from "@/components/PageShell";
import { can } from "@/lib/can";
import { isError } from "@/lib/frappe";
import { getQualityOptions, type QualityOptions } from "@/lib/quality";
import { fmt } from "@/lib/utils";

/**
 * The lab step: one form.
 *
 * A creamery docket comes back a day or two after the milk went out. Pick the
 * milked batch (the ones still awaiting a result come first), fill in what the
 * lab sent back, and the same save writes the bulk SCC, fat and protein onto the
 * batch's milk recordings, so the awaiting list and the SCC ceiling keep working.
 *
 * It exists whether or not the farm captures quality at milking: a figure can
 * always be missing, and a handset never captures quality at all.
 */
export function Quality() {
  const [data, setData] = useState<QualityOptions | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await getQualityOptions();
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setData(r);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const pending = data?.pending ?? [];
  const recent = data?.recent ?? [];
  const flagged = recent.filter((r) => r.over_ceiling).length;

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Milking" title="Quality">
        What comes back from the creamery, filed against the milking batch it belongs
        to. Nothing here moves stock or money — those posted when the milking was
        recorded.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <QualityTrendCard />

      {data && (
        <Notice tone="info">
          {data.mode === "At milking"
            ? "This farm records quality at milking. What is listed as awaiting was left blank at the time, or came in from a handset."
            : "This farm records quality afterwards. Every milking arrives here for its figures."}
          {data.required_in_lab
            ? " A recording stays awaiting until a figure is entered."
            : " Nothing is chased — the list is for reference."}
        </Notice>
      )}

      <FigureRow>
        <Figure label="Awaiting quality" value={String(pending.length)} hint="last 60 days" />
        <Figure label="Filed" value={String(recent.length)} hint="last 60 days" />
        <Figure
          label="Over the ceiling"
          value={String(flagged)}
          hint={data?.scc_ceiling ? `above ${fmt(data.scc_ceiling)} × 1000 cells/ml` : "no ceiling set"}
        />
        <Figure
          label="Captured"
          value={data?.mode === "Afterwards" ? "Afterwards" : "At milking"}
          hint="set in Settings"
        />
      </FigureRow>

      {/* Filing is the lab's and the manager's; whoever may only read sees the results. */}
      <QualityBatch fileable={can.create("Milk Quality Test")} onSaved={load} />
    </Page>
  );
}
