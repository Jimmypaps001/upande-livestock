import { useMemo, useState } from "react";
import { ChevronRight, Layers, Search, X } from "lucide-react";
import { STAGES, ageFrom, type AnimalSummary } from "@/lib/animals";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Find a cow the way you would ask for one.
 *
 * The farm says "A048" or "Hassan" or "the steamers" — a number, a name, or
 * where she is standing — so all three match, and a herd name matching pulls up
 * everyone in it. Anything narrower would mean knowing which of the three you
 * had before you started typing.
 *
 * Nothing is hidden behind a submit. The list narrows as you type and the
 * whole herd is there before you type anything, because "show me everyone in
 * Steamers" is a question people actually have and an empty search box that
 * answers nothing until fed is a worse front door than a list.
 *
 * AND IT GROUPS BY HERD, because that is the other way the farm holds the herd
 * in its head: four hundred cows in one alphabetical column is a list you
 * search, never a list you read. Grouped, it is the farm — nine sheds with
 * counts on them, each opening to who is standing in it. Searching collapses
 * the grouping back to a flat list of matches, since a search already knows
 * what it is looking for.
 */
export function AnimalSearch({
  animals,
  selectedId,
  onSelect,
}: {
  animals: AnimalSummary[];
  selectedId: string | null;
  onSelect: (a: AnimalSummary) => void;
}) {
  const [term, setTerm] = useState("");
  const [byHerd, setByHerd] = useState(false);
  const [shut, setShut] = useState<Record<string, boolean>>({});

  const results = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return animals;
    return animals.filter((a) =>
      [a.id, a.name, a.herd, a.breed || ""].some((f) => f.toLowerCase().includes(q)),
    );
  }, [animals, term]);

  // Grouped only when nothing has been typed: a search already knows what it is
  // looking for, and folding three matches into three herds hides them behind
  // a click each.
  const grouped = useMemo(() => {
    if (!byHerd || term.trim()) return null;
    const sheds = new Map<string, AnimalSummary[]>();
    for (const a of results) {
      const herd = a.herd || "No herd";
      const held = sheds.get(herd);
      if (held) held.push(a);
      else sheds.set(herd, [a]);
    }
    return [...sheds.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [byHerd, term, results]);

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--sd-quiet)]" />
        <Input
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder="Number, name or herd…"
          aria-label="Find an animal"
          className="h-11 rounded-[var(--sd-radius-pill)] border-[var(--sd-line)] bg-[var(--sd-bg-soft)] pl-9 pr-9 text-[13px]"
        />
        {term && (
          <button
            type="button"
            onClick={() => setTerm("")}
            aria-label="Clear the search"
            className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--sd-quiet)] transition-colors hover:text-[var(--sd-ink)]"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 px-1">
        <p className="text-[11.5px] text-[var(--sd-quiet)]">
          {results.length === animals.length
            ? `${animals.length} on the farm`
            : `${results.length} of ${animals.length}`}
        </p>
        <button
          type="button"
          onClick={() => setByHerd((on) => !on)}
          aria-pressed={byHerd}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-[var(--sd-radius-pill)] px-2.5 py-1 text-[11.5px] transition-colors",
            byHerd
              ? "bg-[var(--sd-bg-soft)] text-[var(--sd-ink)]"
              : "text-[var(--sd-muted)] hover:bg-[var(--sd-bg-soft)]",
          )}
        >
          <Layers className="h-3.5 w-3.5" strokeWidth={2} />
          By herd
        </button>
      </div>

      {grouped && (
        <ul className="flex min-h-0 flex-col gap-1 overflow-y-auto">
          {grouped.map(([herd, members]) => (
            <li key={herd} className="flex flex-col">
              <button
                type="button"
                onClick={() => setShut((s) => ({ ...s, [herd]: !s[herd] }))}
                aria-expanded={!shut[herd]}
                className="flex items-center gap-2 rounded-[var(--sd-radius-lg)] px-2 py-2 text-left transition-colors hover:bg-[var(--sd-bg-soft)]"
              >
                <ChevronRight
                  className={cn(
                    "h-3.5 w-3.5 shrink-0 text-[var(--sd-quiet)] transition-transform",
                    !shut[herd] && "rotate-90",
                  )}
                />
                <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-[var(--sd-ink)]">
                  {herd}
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-[var(--sd-quiet)]">
                  {members.length}
                </span>
              </button>
              {!shut[herd] && (
                <ul className="flex flex-col gap-1.5 pl-3">
                  {members.map((a) => (
                    <li key={a.id}>{row(a)}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}

      {!grouped && (
      <ul className="flex min-h-0 flex-col gap-1.5 overflow-y-auto">
        {results.map((a) => {
          const active = a.id === selectedId;
          return (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => onSelect(a)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
                  // The rows live inside a card, so they mark themselves with
                  // fill rather than with lift — a row that cast a card's
                  // shadow inside a card would claim to be above the thing
                  // holding it.
                  active
                    ? "bg-[var(--sd-bg-soft)]"
                    : "hover:bg-[var(--sd-bg-soft)]",
                )}
              >
                <span
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white"
                  style={{ background: STAGES[a.stage].tone }}
                  aria-hidden
                >
                  {a.name.slice(0, 2).toUpperCase()}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="flex items-baseline gap-2">
                    <span className="truncate text-[13.5px] font-medium text-[var(--sd-ink)]">
                      {a.name}
                    </span>
                    <span className="shrink-0 text-[11px] tabular-nums text-[var(--sd-quiet)]">
                      {a.id}
                    </span>
                  </span>
                  <span className="truncate text-[11.5px] text-[var(--sd-muted)]">
                    {a.herd}
                  </span>
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-[var(--sd-quiet)]">
                  {ageFrom(a.bornOn)}
                </span>
              </button>
            </li>
          );
        })}
        {!results.length && (
          <li className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3 py-6 text-center text-[12.5px] text-[var(--sd-muted)]">
            Nobody matches “{term}”. Try a register number, a name, or a herd.
          </li>
        )}
      </ul>
      )}
    </div>
  );

  /** One animal, drawn the same whether she is in a group or a flat list. */
  function row(a: AnimalSummary) {
    const active = a.id === selectedId;
    return (
      <button
        type="button"
        onClick={() => onSelect(a)}
        className={cn(
          "flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
          active ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
        )}
      >
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white"
          style={{ background: STAGES[a.stage].tone }}
          aria-hidden
        >
          {a.name.slice(0, 2).toUpperCase()}
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="flex items-baseline gap-2">
            <span className="truncate text-[13.5px] font-medium text-[var(--sd-ink)]">
              {a.name}
            </span>
            <span className="shrink-0 text-[11px] tabular-nums text-[var(--sd-quiet)]">
              {a.id}
            </span>
          </span>
          <span className="truncate text-[11.5px] text-[var(--sd-muted)]">{a.herd}</span>
        </span>
        <span className="shrink-0 text-[11px] tabular-nums text-[var(--sd-quiet)]">
          {ageFrom(a.bornOn)}
        </span>
      </button>
    );
  }
}
