import { useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isError } from "@/lib/frappe";
import { feedNutrition, hasNutrition, type NutrientLine, type Nutrition } from "@/lib/nutrition";
import { cn, fmt, num } from "@/lib/utils";

const DEBOUNCE_MS = 350;

/**
 * What a recipe contains, live.
 *
 * Used by the Ration Editor, the one screen a recipe is written on, so the
 * numbers are visible wherever a recipe is edited. It computes NOTHING: the
 * lines go to `feed_nutrition` (debounced, so typing a quantity is one call and
 * not one per keystroke) and the answer is drawn as it comes back — including
 * the made feeds the server expanded through their BOMs and the lines it had no
 * data for, which count as zero and are said to.
 *
 * `perUnit` names what the lines are per ("head per day", "batch") so the cost
 * and weight read in the units the farm edits in.
 */
export function NutritionPanel({
  lines,
  perUnit,
  className,
}: {
  lines: NutrientLine[];
  perUnit: string;
  className?: string;
}) {
  const [data, setData] = useState<Nutrition | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [targetCp, setTargetCp] = useState("");
  const [targetMe, setTargetMe] = useState("");
  const seq = useRef(0);

  // A stable key: only a change in what is sent should cost a round trip.
  const key = JSON.stringify(lines.filter((l) => l.item_code && l.qty > 0));

  useEffect(() => {
    const sent = JSON.parse(key) as NutrientLine[];
    if (!sent.length) {
      setData(null);
      setProblem(null);
      return;
    }
    const mine = ++seq.current;
    const t = window.setTimeout(async () => {
      const r = await feedNutrition(sent);
      if (mine !== seq.current) return; // a newer edit is already on its way
      if (isError(r)) {
        setProblem(r.error);
        return;
      }
      setProblem(null);
      if (hasNutrition(r)) setData(r);
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [key]);

  const cp = num(targetCp);
  const me = num(targetMe);

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3.5 shadow-[var(--sd-shadow-inset)]",
        className,
      )}
      data-testid="nutrition-panel"
    >
      <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
        What is in it · per {perUnit}
      </span>

      {problem && <p className="text-[12.5px] text-[var(--sd-sev-critical)]">{problem}</p>}

      {!data ? (
        <p className="text-[12.5px] text-[var(--sd-muted)]">
          Add feeds and amounts to see the nutrition.
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-[13px] sm:grid-cols-3">
            <Stat label="As fed" value={`${fmt(data.as_fed_kg)} kg`} />
            <Stat label="Dry matter" value={`${fmt(data.dm_kg)} kg`} hint={`${fmt(data.dm_pct)}%`} />
            <Stat label="Cost" value={fmt(data.cost)} />
            <Stat label="Crude protein" value={`${fmt(data.cp_pct)}%`} hint="of DM" />
            <Stat label="Carbohydrate" value={`${fmt(data.carbohydrate_pct)}%`} hint="non-fibre, of DM" />
            <Stat label="NDF" value={`${fmt(data.ndf_pct)}%`} hint="of DM" />
            <Stat label="Fat" value={`${fmt(data.fat_pct)}%`} hint="of DM" />
            <Stat label="Energy (ME)" value={`${fmt(data.me_mj_per_kg)}`} hint="MJ/kg DM" />
            <Stat label="Ca / P" value={`${fmt(data.ca_pct)} / ${fmt(data.p_pct)}%`} hint="of DM" />
          </dl>

          {/* Targets are the farm's own numbers, typed to compare against — not
              stored, and not a standard this app knows. */}
          <div className="flex flex-wrap items-end gap-3 border-t border-[var(--sd-line)] pt-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="np-cp" className="text-[11px]">Target CP %</Label>
              <Input id="np-cp" type="number" min={0} step="any" className="h-8 w-24"
                     value={targetCp} onChange={(e) => setTargetCp(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="np-me" className="text-[11px]">Target ME (MJ/kg DM)</Label>
              <Input id="np-me" type="number" min={0} step="any" className="h-8 w-28"
                     value={targetMe} onChange={(e) => setTargetMe(e.target.value)} />
            </div>
            {cp > 0 && <Compare label="CP" actual={data.cp_pct} target={cp} unit="%" />}
            {me > 0 && <Compare label="ME" actual={data.me_mj_per_kg} target={me} unit=" MJ" />}
          </div>

          {data.lines.some((l) => l.made) && (
            <ul className="flex flex-col gap-0.5 text-[12px] text-[var(--sd-muted)]">
              {data.lines
                .filter((l) => l.made)
                .map((l) => (
                  <li key={l.item_code}>
                    {l.item_name} is worked out from its own recipe
                    {l.computed ? ` (CP ${fmt(l.computed.cp_pct)}%, ME ${fmt(l.computed.me_mj_per_kg)})` : ""}
                    {l.lab_check?.cp_pct != null
                      ? ` · lab check CP ${fmt(l.lab_check.cp_pct)}%`
                      : ""}
                    .
                  </li>
                ))}
            </ul>
          )}

          {data.missing.length > 0 && (
            <div
              role="status"
              className="flex items-start gap-2 rounded-[var(--sd-radius-toast)] bg-[var(--sd-alert-warn)] px-3 py-2.5 text-[12.5px] leading-relaxed text-[var(--sd-ink)]"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--sd-sev-high)" }} />
              <span>
                No nutrient data for{" "}
                {data.missing
                  .map((m) => `${m.item_name}${m.via ? ` (in ${m.via})` : ""}`)
                  .join(", ")}
                . It counts as zero, so these figures read low. Fill its Livestock Feed record in.
              </span>
            </div>
          )}
          {data.unpriced.length > 0 && (
            <p className="text-[12px] text-[var(--sd-muted)]">
              No price for {data.unpriced.map((u) => u.item_name).join(", ")}; the cost leaves it out.
            </p>
          )}
          {!!data.doses?.length && (
            <p className="text-[12px] text-[var(--sd-muted)]">
              Doses a head, not in these figures:{" "}
              {data.doses
                .map((d) => `${d.item_name} ${fmt(d.qty)} ${d.uom === "Gram" ? "g" : d.uom === "Millilitre" ? "ml" : d.uom}`)
                .join(", ")}
              .
            </p>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex min-w-0 flex-col">
      <dt className="text-[11px] text-[var(--sd-quiet)]">{label}</dt>
      <dd className="font-semibold tabular-nums text-[var(--sd-ink)]">
        {value}
        {hint && <span className="ml-1 text-[11px] font-normal text-[var(--sd-muted)]">{hint}</span>}
      </dd>
    </div>
  );
}

function Compare({ label, actual, target, unit }: { label: string; actual: number; target: number; unit: string }) {
  const diff = actual - target;
  const ok = Math.abs(diff) < 0.005 * target || diff >= 0;
  return (
    <span
      className={cn(
        "pb-1.5 text-[12.5px] font-medium tabular-nums",
        ok ? "text-[var(--sd-sev-moderate)]" : "text-[var(--sd-sev-critical)]",
      )}
    >
      {label} {diff >= 0 ? "+" : ""}
      {fmt(diff)}
      {unit} vs target
    </span>
  );
}
