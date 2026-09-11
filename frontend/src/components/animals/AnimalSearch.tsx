import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";
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

  const results = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return animals;
    return animals.filter((a) =>
      [a.id, a.name, a.herd, a.breed || ""].some((f) => f.toLowerCase().includes(q)),
    );
  }, [animals, term]);

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

      <p className="px-1 text-[11.5px] text-[var(--sd-quiet)]">
        {results.length === animals.length
          ? `${animals.length} on the farm`
          : `${results.length} of ${animals.length}`}
      </p>

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
    </div>
  );
}
