import { useState } from "react";
import { InsureDialog, canInsure } from "@/components/animals/InsureDialog";
import { STAGES, ageFrom, initialsOf, type AnimalProfile } from "@/lib/animals";
import { SilhouetteFrame } from "@/components/animals/AnimalSilhouette";
import { CoverBadge } from "@/components/animals/CoverBadge";
import { cn } from "@/lib/utils";

/**
 * Her photograph, and the four facts you would say out loud to identify her.
 *
 * The frame is 4:5 and it is kept whether or not there is a picture in it. A
 * panel that collapsed when the photo was missing would reflow the whole right
 * rail the moment somebody added one, and most of this herd has no photo yet —
 * the empty state is the common case, so it has to be a deliberate surface
 * rather than a gap.
 */
export function AnimalPortrait({ animal, onInsured }: { animal: AnimalProfile; onInsured?: () => void }) {
  const [insuring, setInsuring] = useState(false);
  const mayInsure =
    canInsure() && (animal.cover === "none" || animal.cover === "expired");
  // The date of her latest weighing, from the timeline (the profile lists every weighing).
  const lastWeighed = [...(animal.milestones ?? [])].reverse().find((m) => m.kind === "weight")?.on ?? null;
  const stage = STAGES[animal.stage];
  return (
    <div className="flex flex-col gap-4">
      <div
        className={cn(
          "relative aspect-[4/5] w-full overflow-hidden rounded-[var(--sd-radius-card)]",
          "bg-[var(--sd-bg-soft)] shadow-[var(--sd-shadow-1)]",
        )}
      >
        {animal.photo ? (
          <img
            src={animal.photo}
            decoding="async"
            alt={`${animal.name}, ${animal.id}`}
            className="h-full w-full object-cover"
          />
        ) : (
          // A silhouette picked by species, age, sex and stage (and a pose by her
          // number), not an apology. Most of this herd has no photograph and
          // probably never will; a panel that said so on every animal would be
          // reporting the same absence three hundred times. Set in the stage's
          // own colour so the frame still identifies her at a glance.
          <SilhouetteFrame
            animal={animal}
            tone={stage.tone}
            className="h-full w-full pb-[18%]"
            label={`${animal.name} — no photograph; ${stage.label.toLowerCase()} ${animal.sex === "Male" ? "male" : "female"}`}
          />
        )}

        {/* The number, on the picture. It is what she is called on paper, in the
            parlour and in every other screen in this app. */}
        <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 bg-gradient-to-t from-[rgba(10,10,10,0.72)] to-transparent px-4 pb-3.5 pt-10">
          <div className="min-w-0">
            <p className="truncate text-[19px] font-semibold leading-tight tracking-[-0.02em] text-white">
              {animal.name}
            </p>
            <p className="text-[12px] tabular-nums text-white/70">{animal.id}</p>
          </div>
          <span
            className="shrink-0 rounded-[var(--sd-radius-pill)] px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-white"
            style={{ background: stage.tone }}
          >
            {stage.label}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 text-[12px] text-[var(--sd-muted)]">
        <CoverBadge state={animal.cover} detail info={animal.coverDetail} />
        {animal.coverDetail?.end && animal.cover !== "none" && (
          <span>
            {animal.cover === "expired" ? "ended" : "until"} {animal.coverDetail.end}
          </span>
        )}
        {mayInsure && (
          <button
            type="button"
            className="ml-auto rounded-[var(--sd-radius-pill)] border border-[var(--sd-line)] px-2.5 py-1 text-[11px] font-medium text-[var(--sd-ink)] hover:bg-[var(--sd-card)]"
            onClick={() => setInsuring(true)}
          >
            Insure
          </button>
        )}
        {mayInsure && (
          <InsureDialog open={insuring} onOpenChange={setInsuring} animal={animal.id} sex={animal.sex} onInsured={onInsured} />
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Fact label="Age" value={ageFrom(animal.bornOn) + (animal.bornEstimated ? " (est.)" : "")} />
        <Fact label="Breed" value={animal.breed || "—"} />
        <Fact label="Herd" value={animal.herd} />
        <Fact label="Sex" value={animal.sex || "—"} />
        <Fact label="Dam" value={animal.dam || "—"} />
        <Fact label="Sire" value={animal.sire || "—"} />
        <Fact label="Last served" value={lastServed(animal)} />
        <Fact label="Last weighed" value={lastWeighed ?? "—"} />
      </dl>
    </div>
  );
}

/** "STORMER · 2026-11-17": who inseminated her last, and the day. */
export function lastServed(animal: Pick<AnimalProfile, "lastService">): string {
  const s = animal.lastService;
  if (!s) return "—";
  const who = s.sire || (s.type ? `${s.type}, bull not recorded` : "bull not recorded");
  return `${who} · ${s.on}${s.estimated ? " (est.)" : ""}`;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-[10px] font-medium uppercase tracking-[0.13em] text-[var(--sd-quiet)]">
        {label}
      </dt>
      <dd className="truncate text-[13px] text-[var(--sd-ink)]" title={value}>
        {value}
      </dd>
    </div>
  );
}


export function AnimalPortraitSkeleton() {
  // The portrait is aspect-[4/5] of the rail's width; matching the aspect
  // rather than a pixel height keeps it right at every breakpoint.
  return (
    <div
      className="aspect-[4/5] w-full animate-pulse rounded bg-[var(--sd-bg-soft)] !rounded-[var(--sd-radius-card)]"
      aria-hidden
    />
  );
}
