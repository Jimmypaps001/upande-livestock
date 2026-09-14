import { useCallback } from "react";
import { Page, PageHeading } from "@/components/PageShell";
import { RecordEvent, type FieldSpec } from "@/components/events/RecordEvent";
import { createMovementEvent, getMovementOptions, type MovementOptions } from "@/lib/events";

/**
 * Moving one animal between herds.
 *
 * The same act the Herds page performs in bulk, for the ordinary case of one
 * cow going one place. It writes a Movement event rather than the animal's
 * `current_herd`, so her record can always say who moved her and when — which
 * is the whole reason nothing in this app sets that field directly.
 */
export function Movement() {
  const load = useCallback(() => getMovementOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Herd" title="Movement">
        One animal, one herd to another. Her history keeps the move, so where
        she stood in March is still an answerable question.
      </PageHeading>
      <RecordEvent<MovementOptions>
        eyebrow="Herd"
        title="a movement"
        blurb="Any animal on the farm."
        pickLabel="Which animal"
        emptyPick="No animals on this site."
        load={load}
        animalsOf={(o) => o.animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "event_date", label: "Moved on", kind: "date" },
          { name: "new_herd", label: "Moving to", kind: "select",
            options: o.herds.map((h) => h.name), required: true },
          { name: "remarks", label: "Why", kind: "notes",
            placeholder: "Coming into milk." },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Move her"
        submit={createMovementEvent}
        said={(r, a) => `${a} moved — ${r.name}.`}
      />
    </Page>
  );
}
