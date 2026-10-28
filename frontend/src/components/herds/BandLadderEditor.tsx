import { useEffect, useState } from "react";
import { Notice } from "@/components/feeding/Notice";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { isError } from "@/lib/frappe";
import { ladderRows, saveBandLadder, validateLadder, type HerdBand, type LadderRow } from "@/lib/herds";

/**
 * All the fattening bands in one place, lowest first.
 *
 * Two neighbouring bands share a boundary, so moving it means editing both
 * herds; saved one at a time the first save is always an overlap or a gap. Here
 * every rung is edited and saved together, and the server judges the whole
 * ladder once.
 */
export function BandLadderEditor({
  bands,
  loading,
  onDone,
}: {
  bands: HerdBand[];
  loading: boolean;
  onDone: (message: string) => void;
}) {
  const [rows, setRows] = useState<LadderRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    setRows(ladderRows(bands));
    setFailure(null);
  }, [bands]);

  const edit = (herd: string, patch: Partial<LadderRow>) =>
    setRows((rs) => rs.map((r) => (r.herd === herd ? { ...r, ...patch } : r)));

  async function submit() {
    const problem = validateLadder(rows);
    if (problem) {
      setFailure(problem);
      return;
    }
    setBusy(true);
    setFailure(null);
    const r = await saveBandLadder(rows);
    setBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    onDone(`The weight bands are saved (${r.bands.length} herds).`);
  }

  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Edit bands</CardTitle>
          <CardDescription>
            Every fattening herd in weight order. Move a shared boundary by changing the top of one
            band and the bottom of the next, then save them together.
          </CardDescription>
        </CardHeading>
      </CardHeaderRow>
      <CardContent className="flex flex-col gap-4 pt-0">
        {loading && !rows.length ? (
          <Skeleton className="h-24 w-full" />
        ) : !rows.length ? (
          <p className="text-[13px] text-[var(--sd-quiet)]">There are no fattening herds yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {rows.map((r) => (
              <div key={r.herd} className="grid items-center gap-3 sm:grid-cols-[minmax(0,1fr)_repeat(3,7.5rem)]">
                <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">{r.herd}</span>
                <Input
                  aria-label={`${r.herd} from (kg)`}
                  type="number"
                  min={0}
                  inputMode="decimal"
                  value={r.min}
                  onChange={(e) => edit(r.herd, { min: e.target.value })}
                />
                <Input
                  aria-label={`${r.herd} up to (kg)`}
                  type="number"
                  min={0}
                  inputMode="decimal"
                  placeholder="Top"
                  value={r.max}
                  onChange={(e) => edit(r.herd, { max: e.target.value })}
                />
                <Input
                  aria-label={`${r.herd} target gain (kg/day)`}
                  type="number"
                  min={0}
                  step="0.01"
                  inputMode="decimal"
                  value={r.target}
                  onChange={(e) => edit(r.herd, { target: e.target.value })}
                />
              </div>
            ))}
          </div>
        )}

        {failure && <Notice tone="error">{failure}</Notice>}

        <div>
          <Button onClick={submit} disabled={busy || !rows.length}>
            {busy ? "Saving…" : "Save the bands"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
