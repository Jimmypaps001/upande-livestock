import { Camera } from "lucide-react";
import { STAGES, ageFrom, type AnimalProfile } from "@/lib/animals";
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
export function AnimalPortrait({ animal }: { animal: AnimalProfile }) {
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
            alt={`${animal.name}, ${animal.id}`}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2.5 text-[var(--sd-quiet)]">
            <Camera className="h-7 w-7" strokeWidth={1.25} />
            <span className="text-[11.5px]">No photograph yet</span>
          </div>
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

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Fact label="Age" value={ageFrom(animal.bornOn)} />
        <Fact label="Breed" value={animal.breed || "—"} />
        <Fact label="Herd" value={animal.herd} />
        <Fact label="Sex" value={animal.sex} />
        <Fact label="Dam" value={animal.dam || "—"} />
        <Fact label="Sire" value={animal.sire || "—"} />
      </dl>
    </div>
  );
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
