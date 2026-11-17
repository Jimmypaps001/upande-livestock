import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CheckCircle } from "@/components/ui/check-circle";
import { Picker } from "@/components/ui/picker";
import type { AnimalChoice } from "@/lib/events";
import { cn } from "@/lib/utils";

/**
 * Who this is being done to: one animal, a set of them, or a whole herd.
 *
 * DOSING IS A ROUND. Nobody vaccinates one cow and comes back tomorrow for the
 * next; a vaccination morning is a herd through a crush. The screens asked for
 * one animal at a time, which made the commonest job on the farm the one thing
 * the app could not do — while the endpoint behind them has taken a set or a
 * herd all along.
 *
 * A HERD IS A WAY OF FINDING THEM, not a different kind of record. The server
 * fans a herd round out into one event per animal, because a withdrawal date
 * and a next-due date are facts about a cow and not about a pen. Choosing a
 * herd shows its animals and ticks none of them: it used to tick the whole herd,
 * and every herd chosen after it added its animals on top, so a look at another
 * herd picked that herd too. "Select all N shown" ticks the herd in one go.
 */
export function TargetPicker({
  animals,
  herds,
  picked,
  onChange,
  label = "Who this is for",
}: {
  animals: AnimalChoice[];
  herds: { name: string; label?: string; heads?: number }[];
  picked: string[];
  onChange: (next: string[]) => void;
  label?: string;
}) {
  const [term, setTerm] = useState("");
  const [herd, setHerd] = useState("");

  const results = useMemo(() => {
    const q = term.trim().toLowerCase();
    const base = herd ? animals.filter((a) => a.herd === herd) : animals;
    if (!q) return base;
    return base.filter((a) =>
      [a.name, a.label, a.herd_label || a.herd || ""].some((f) => f.toLowerCase().includes(q)),
    );
  }, [animals, term, herd]);

  const chosen = new Set(picked);
  const shown = results.map((a) => a.name);
  const allShown = shown.length > 0 && shown.every((id) => chosen.has(id));

  function toggle(id: string) {
    const next = new Set(chosen);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange([...next]);
  }

  return (
    <div className="flex flex-col gap-2">
      <Label>{label}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <Picker
          value={herd}
          // Shows the herd's animals; ticking stays with the operator.
          onChange={setHerd}
          options={herds.map((h) => ({
            value: h.name,
            label: h.heads != null ? `${h.label || h.name} (${h.heads})` : h.label || h.name,
          }))}
          placeholder="A whole herd…"
          clearable
          clearLabel="Every herd"
          label="Pick a whole herd"
          className="w-[210px]"
        />
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--sd-quiet)]" />
          <Input
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder="Number or name…"
            aria-label="Find an animal"
            className="h-9 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] pl-9 text-[13px]"
          />
        </div>
        <button
          type="button"
          disabled={!shown.length}
          onClick={() =>
            onChange(
              allShown
                ? picked.filter((id) => !shown.includes(id))
                : [...new Set([...picked, ...shown])],
            )
          }
          className="text-[12px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)] disabled:opacity-40"
        >
          {allShown ? "Unpick all shown" : `Select all ${shown.length} shown`}
        </button>
        <span className="text-[11.5px] tabular-nums text-[var(--sd-quiet)]">
          {picked.length} picked
        </span>
      </div>

      <ul className="flex max-h-[280px] flex-col gap-0.5 overflow-y-auto rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] p-1 shadow-[var(--sd-shadow-inset)]">
        {!results.length ? (
          <li className="px-3 py-2 text-[12.5px] text-[var(--sd-muted)]">Nobody matches that.</li>
        ) : (
          results.map((a) => {
            const on = chosen.has(a.name);
            return (
              <li key={a.name}>
                <div
                  className={cn(
                    "flex items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2 transition-colors",
                    on ? "bg-[var(--sd-card)]" : "hover:bg-[var(--sd-card)]",
                  )}
                >
                  <CheckCircle checked={on} onCheckedChange={() => toggle(a.name)} label={a.label} />
                  <button
                    type="button"
                    onClick={() => toggle(a.name)}
                    className="flex min-w-0 flex-1 flex-col text-left"
                  >
                    <span className="truncate text-[13px] text-[var(--sd-ink)]">{a.label}</span>
                    <span className="truncate text-[11px] text-[var(--sd-quiet)]">
                      {a.herd_label || a.herd || "no herd"}
                    </span>
                  </button>
                </div>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
