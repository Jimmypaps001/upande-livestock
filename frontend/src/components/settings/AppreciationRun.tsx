import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Button } from "@/components/ui/button";
import { isError } from "@/lib/frappe";
import { runAppreciation, type AppreciationSummary } from "@/lib/appreciation";

const KES = (n: number) => `KES ${Math.round(n).toLocaleString()}`;

/**
 * "Run now" for asset appreciation. The dry run reports what would be posted
 * and writes nothing; the real run posts Asset Value Adjustments and asks
 * first, because it moves money in the books.
 */
export function AppreciationRun({ canRun }: { canRun: boolean }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [summary, setSummary] = useState<AppreciationSummary | null>(null);

  async function go(dry: boolean) {
    if (!dry && !window.confirm("Post the appreciation now? This books Asset Value Adjustments.")) return;
    setBusy(true);
    setFailure(null);
    const result = await runAppreciation(dry);
    setBusy(false);
    if (isError(result)) {
      setFailure(result.error);
      setSummary(null);
      return;
    }
    setSummary(result);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" disabled={!canRun || busy} onClick={() => go(true)}>
          Run now (dry run)
        </Button>
        <Button size="sm" disabled={!canRun || busy} onClick={() => go(false)}>
          Run now
        </Button>
        {busy && <Loader2 className="h-4 w-4 animate-spin" />}
        <span className="text-[12px] text-[var(--sd-muted)]">
          Save any settings changes first; a run reads what is saved.
        </span>
      </div>

      {failure && <Notice tone="error">{failure}</Notice>}

      {summary && (
        <Notice tone="ok">
          <p className="font-semibold">
            {summary.dry_run ? "Dry run" : "Posted"}: {summary.animals} animals checked,{" "}
            {summary.counts.posted ?? summary.counts.would_post ?? 0}{" "}
            {summary.dry_run ? "would change" : "changed"}, net {KES(summary.net)}.
          </p>
          {Object.keys(summary.skipped_reasons).length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-[12px]">
              {Object.entries(summary.skipped_reasons).map(([reason, n]) => (
                <li key={reason}>
                  {n} × {reason}
                </li>
              ))}
            </ul>
          )}
        </Notice>
      )}
    </div>
  );
}
