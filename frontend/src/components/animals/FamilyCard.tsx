import { useEffect, useState } from "react";
import { getAnimalFamily, type AnimalFamily, type Relative } from "@/lib/animals-api";
import { isError } from "@/lib/frappe";
import { Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Her family: dam and sire above, every calf below (sold and dead ones too,
 * greyed, with what became of them). A bull also gets his record as a sire.
 * Reads `animal_family`, which asks the record rather than the phone's store,
 * so a calf that left the farm is still on its mother's page.
 */
export function FamilyCard({ animal, onOpen }: { animal: string; onOpen: (id: string) => void }) {
  const [family, setFamily] = useState<AnimalFamily | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void getAnimalFamily(animal).then((r) => {
      if (!live) return;
      if (isError(r) || !Array.isArray((r as AnimalFamily)?.offspring)) setFailed(true);
      else setFamily(r);
    });
    return () => {
      live = false;
    };
  }, [animal]);

  if (failed) return null;
  const { parents, offspring, bred } = family ?? { parents: { dam: null, sire: null }, offspring: [], bred: null };

  return (
    <Card>
      <CardHeaderRow className="pb-0">
        <CardHeading>
          <CardTitle className="text-[14px]">Family</CardTitle>
          <CardDescription>
            {family
              ? offspring.length
                ? `${offspring.length} ${offspring.length === 1 ? "calf" : "calves"} (${family.sons} bull, ${family.daughters} heifer)`
                : "No calves on record."
              : "Loading…"}
          </CardDescription>
        </CardHeading>
      </CardHeaderRow>
      <CardContent className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3">
          <Parent label="Dam" who={parents.dam} onOpen={onOpen} />
          <Parent label="Sire" who={parents.sire} onOpen={onOpen} />
        </div>
        {bred && (
          <p className="text-[12.5px] text-[var(--sd-muted)]">
            Sire of record: {bred.services} {bred.services === 1 ? "service" : "services"} on {bred.cows}{" "}
            {bred.cows === 1 ? "cow" : "cows"}
            {bred.conceptionRate != null ? `, ${bred.conceptionRate}% conceived` : ""}
            {bred.lastService ? `, last ${bred.lastService}` : ""}.
          </p>
        )}
        {offspring.length > 0 && (
          <ul className="flex max-h-56 flex-col overflow-y-auto">
            {offspring.map((o) => (
              <li key={o.id ?? o.name}>
                <button
                  type="button"
                  disabled={!o.onRecord || !o.active}
                  onClick={() => o.id && onOpen(o.id)}
                  className={cn(
                    "flex w-full items-baseline justify-between gap-2 rounded-[var(--sd-radius)] px-2 py-1.5 text-left text-[12.5px]",
                    o.active ? "hover:bg-[var(--sd-bg-soft)]" : "text-[var(--sd-quiet)]",
                  )}
                >
                  <span className="truncate">
                    {o.name} <span className="tabular-nums text-[var(--sd-quiet)]">{o.id}</span>
                  </span>
                  <span className="shrink-0 text-[11px] text-[var(--sd-quiet)]">
                    {o.active ? o.dob ?? "" : o.status ?? "left the farm"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Parent({ label, who, onOpen }: { label: string; who: Relative | null; onOpen: (id: string) => void }) {
  const open = !!who?.id && who.onRecord && who.active;
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="text-[10px] font-medium uppercase tracking-[0.13em] text-[var(--sd-quiet)]">{label}</span>
      {who ? (
        <button
          type="button"
          disabled={!open}
          onClick={() => who.id && onOpen(who.id)}
          className={cn("truncate text-left text-[13px]", open ? "text-[var(--sd-ink)] hover:underline" : "text-[var(--sd-muted)]")}
          title={who.name}
        >
          {who.name}
        </button>
      ) : (
        <span className="text-[13px] text-[var(--sd-muted)]">—</span>
      )}
    </div>
  );
}
