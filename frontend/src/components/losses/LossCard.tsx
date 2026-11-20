import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle } from "@/components/ui/card";
import { Notice } from "@/components/feeding/Notice";
import { RecordLossDialog } from "@/components/losses/RecordLossDialog";
import { isError } from "@/lib/frappe";
import { getLossTrail, trailSteps, type LossTrail } from "@/lib/losses";

const LEFT = ["Dead", "Sold", "Culled", "Transferred Out"];

/**
 * "Loss & claim": the trail of each loss of this animal (incident, claim,
 * disposal, invoice, settlement) and the way to record a new one.
 */
export function LossCard({ animal, status, onChanged }: { animal: string; status?: string; onChanged?: () => void }) {
  const [losses, setLosses] = useState<LossTrail[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const mayRecord = !status || !LEFT.includes(status);

  const load = useCallback(async () => {
    const r = await getLossTrail(animal);
    if (isError(r)) setError(r.error);
    else {
      setError(null);
      setLosses(r.losses);
    }
  }, [animal]);

  useEffect(() => {
    setLosses(null);
    void load();
  }, [load]);

  // Nothing to show and nothing to do: the card stays out of the way.
  if (losses && losses.length === 0 && !mayRecord) return null;

  return (
    <Card>
      <CardHeaderRow className="pb-0">
        <CardHeading>
          <CardTitle className="text-[14px]">Loss &amp; claim</CardTitle>
          <CardDescription>Injury, sickness, death or theft, and the insurance claim behind it.</CardDescription>
        </CardHeading>
        {mayRecord && (
          <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
            Record a loss
          </Button>
        )}
      </CardHeaderRow>
      <CardContent className="grid gap-4 pt-3">
        {error && <Notice tone="error">{error}</Notice>}
        {losses && losses.length === 0 && <p className="text-[12px] text-[var(--sd-muted)]">No loss recorded.</p>}
        {(losses ?? []).map((t) => (
          <div key={t.name} className="grid gap-2" data-testid="loss-trail">
            <p className="text-[12.5px] font-medium">
              {t.name} · {t.status}
            </p>
            {t.waiting_for && <Notice tone="info">{t.waiting_for}</Notice>}
            <ol className="grid gap-1">
              {trailSteps(t).map((s) => (
                <li key={s.label} className="flex gap-2 text-[12px]">
                  <span aria-hidden>{s.done ? "●" : "○"}</span>
                  <span className="w-20 shrink-0 font-medium">{s.label}</span>
                  <span className="min-w-0 text-[var(--sd-muted)]">{s.detail}</span>
                </li>
              ))}
            </ol>
            {t.claim && t.claim.missing_documents.length > 0 && (
              <p className="text-[11.5px] text-[var(--sd-muted)]">Still to attach: {t.claim.missing_documents.join(", ")}.</p>
            )}
          </div>
        ))}
      </CardContent>
      {mayRecord && (
        <RecordLossDialog
          open={open}
          onOpenChange={setOpen}
          animal={animal}
          onRecorded={() => {
            void load();
            onChanged?.();
          }}
        />
      )}
    </Card>
  );
}
