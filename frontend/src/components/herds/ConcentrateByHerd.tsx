import { useState } from "react";
import { Notice } from "@/components/feeding/Notice";
import { Badge } from "@/components/ui/badge";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle,
} from "@/components/ui/card";
import { Picker } from "@/components/ui/picker";
import { isError } from "@/lib/frappe";
import {
  CONCENTRATE_MODES, resolvePremanufacture, setHerdConcentrateMode, type ConcentrateMode,
} from "@/lib/herds";

export type HerdConcentrateRow = { herd: string; concentrate_mode?: ConcentrateMode | null };

/**
 * Herd by herd: does it eat a concentrate mixed ahead for the store, or is its
 * ration mixed straight from raw ingredients?
 *
 * THE RULE, said once on the page so nobody has to guess: a herd on "Farm
 * default" follows Livestock Settings > Pre-manufacture Concentrate; the other
 * two answers override it for that herd. The Concentrate window is shown while
 * at least one herd ends up eating a pre-made concentrate — Mutara mixes its
 * cattle from raw and keeps the window only for the shoats' batch.
 */
export function ConcentrateByHerd({
  herds,
  farmOn,
  loading,
  canWrite = true,
  onDone,
}: {
  herds: HerdConcentrateRow[];
  /** Livestock Settings > Pre-manufacture Concentrate. */
  farmOn: boolean;
  loading: boolean;
  canWrite?: boolean;
  onDone: (message: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const inUse = herds.length
    ? herds.some((h) => resolvePremanufacture(h.concentrate_mode, farmOn))
    : farmOn;

  async function change(herd: string, mode: ConcentrateMode) {
    setBusy(herd);
    setFailure(null);
    const r = await setHerdConcentrateMode(herd, mode);
    setBusy(null);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    const eats = resolvePremanufacture(mode, farmOn);
    onDone(
      `${herd} ${eats ? "eats a pre-made concentrate" : "is mixed from raw ingredients"}${
        mode === "Farm default" ? " (the farm default)" : ""
      }. Reload the app to update the sidebar.`,
    );
  }

  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Concentrate, herd by herd</CardTitle>
          <CardDescription>
            Whether each herd eats a concentrate mixed ahead for the store, or has its ration
            mixed straight from raw ingredients. &ldquo;Farm default&rdquo; follows Settings &rarr;
            Pre-manufacture Concentrate, which is <strong>{farmOn ? "on" : "off"}</strong>. The
            Concentrate window is shown while at least one herd eats a pre-made concentrate
            {herds.length ? <> &mdash; right now it is <strong>{inUse ? "shown" : "hidden"}</strong></> : null}.
          </CardDescription>
        </CardHeading>
      </CardHeaderRow>
      <CardContent className="flex flex-col gap-2 pt-0">
        {failure && <Notice tone="error">{failure}</Notice>}
        {loading && !herds.length && (
          <p className="text-[13px] text-[var(--sd-muted)]">Reading herds…</p>
        )}
        <ul className="flex flex-col divide-y divide-[var(--sd-line)]">
          {herds.map((h) => {
            const mode = (h.concentrate_mode || "Farm default") as ConcentrateMode;
            const eats = resolvePremanufacture(mode, farmOn);
            return (
              <li key={h.herd} className="flex flex-wrap items-center gap-3 py-2">
                <span className="min-w-[140px] flex-1 text-[13px] font-medium text-[var(--sd-ink)]">
                  {h.herd}
                </span>
                <Badge variant={eats ? "default" : "outline"}>
                  {eats ? "pre-made concentrate" : "mixed from raw"}
                </Badge>
                <Picker
                  id={`cm-${h.herd}`}
                  value={mode}
                  onChange={(next) => next && void change(h.herd, next as ConcentrateMode)}
                  options={CONCENTRATE_MODES.map((m) => ({ value: m, label: m }))}
                  label={`Concentrate for ${h.herd}`}
                  className="w-44"
                  disabled={!canWrite || busy === h.herd}
                />
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
