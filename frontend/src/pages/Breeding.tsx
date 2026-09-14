import { useCallback } from "react";
import { Page, PageHeading } from "@/components/PageShell";
import { RecordEvent, type FieldSpec } from "@/components/events/RecordEvent";
import {
  createAbortionEvent,
  createDryingOffEvent,
  createHeatEvent,
  createPregnancyDiagnosis,
  createServiceEvent,
  getBreedingOptions,
  getHealthOptions,
  getMovementOptions,
  type BreedingOptions,
  type HealthOptions,
  type MovementOptions,
} from "@/lib/events";

/**
 * The breeding calendar, one screen per thing that happens to a cow.
 *
 * Each is the same scaffold with a different animal list, and the list is the
 * point: the server decides who may be served (past the post-calving wait, on
 * the right rung of the ladder) and who may be diagnosed (an open service to
 * answer). A "Confirmed" invented for a cow nobody served goes on to drive
 * calving, herd moves and milk, so the narrowing is not cosmetic.
 */

export function Service() {
  const load = useCallback(() => getBreedingOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Breeding" title="Service">
        Record an insemination or a natural service. Only cows past the farm's
        post-calving wait are offered — serving one earlier is a service the
        calendar cannot answer for.
      </PageHeading>
      <RecordEvent<BreedingOptions>
        eyebrow="Breeding"
        title="a service"
        blurb="Cows the farm may serve today."
        pickLabel="Ready to serve"
        emptyPick="No cow is ready to serve. They are either too soon after calving or already carrying."
        load={load}
        animalsOf={(o) => o.animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "service_date", label: "Service date", kind: "date" },
          { name: "service_type", label: "How", kind: "select", options: o.service_types, required: true },
          { name: "sire", label: "Sire", kind: "select", options: o.sires,
            hint: "Or leave blank and note it below." },
          { name: "semen_item", label: "Straw used", kind: "select",
            options: o.semen_items.map((i) => i.item_code),
            hint: "Issued from the semen store when chosen." },
          { name: "remarks", label: "Notes", kind: "notes",
            placeholder: "Standing heat at 6am, served at 4pm." },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Record the service"
        submit={createServiceEvent}
        said={(r, a) => `${a} served — ${r.name}. The pregnancy check is due on the farm's own interval.`}
      />
    </Page>
  );
}

export function Diagnosis() {
  const load = useCallback(() => getBreedingOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Breeding" title="Pregnancy diagnosis">
        The answer to a question a service asked. Only cows with an open service
        are offered.
      </PageHeading>
      <RecordEvent<BreedingOptions>
        eyebrow="Breeding"
        title="a diagnosis"
        blurb="Cows waiting on a check."
        pickLabel="Awaiting a check"
        emptyPick="Nothing is awaiting a pregnancy check."
        load={load}
        animalsOf={(o) => o.diagnosis_animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "diagnosis_date", label: "Checked on", kind: "date" },
          { name: "diagnosis_result", label: "Result", kind: "select",
            options: o.diagnosis_results, required: true },
          { name: "diagnosis_remarks", label: "Notes", kind: "notes",
            placeholder: "Scanned; roughly 45 days." },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Record the result"
        submit={createPregnancyDiagnosis}
        said={(r, a) => `${a} checked — ${r.name}.`}
      />
    </Page>
  );
}

export function Abortion() {
  const load = useCallback(() => getHealthOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Breeding" title="Abortion">
        A pregnancy lost. Recorded against the pregnancy it ends, so her
        calendar and her history both stop expecting a calf.
      </PageHeading>
      <RecordEvent<HealthOptions>
        eyebrow="Breeding"
        title="an abortion"
        blurb="Any animal on the farm."
        pickLabel="Which cow"
        emptyPick="No animals on this site."
        load={load}
        animalsOf={(o) => o.animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "event_date", label: "When", kind: "date" },
          { name: "abortion_cause", label: "Cause", kind: "select", options: o.abortion_causes },
          { name: "abortion_notes", label: "What happened", kind: "notes",
            placeholder: "Found the foetus in the morning; she is eating." },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Record the loss"
        submit={createAbortionEvent}
        said={(r, a) => `Recorded against ${a} — ${r.name}. Her pregnancy is closed.`}
      />
    </Page>
  );
}

export function DryingOff() {
  const load = useCallback(() => getMovementOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Breeding" title="Drying off">
        Taking a cow out of milk before she calves. She moves to the herd that
        steams her up, and any drying-off treatment goes out of the store with
        her.
      </PageHeading>
      <RecordEvent<MovementOptions>
        eyebrow="Breeding"
        title="a drying off"
        blurb="Cows in milk."
        pickLabel="Which cow"
        emptyPick="No animals on this site."
        load={load}
        animalsOf={(o) => o.animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "event_date", label: "Dried off on", kind: "date" },
          { name: "new_herd", label: "Moving to", kind: "select",
            options: o.herds.map((h) => h.name),
            hint: "Leave blank to let the farm's own rule decide." },
          { name: "remarks", label: "Notes", kind: "notes" },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Dry her off"
        submit={createDryingOffEvent}
        said={(r, a) => `${a} is dry — ${r.name}.`}
      />
    </Page>
  );
}

export function Heat() {
  const load = useCallback(() => getBreedingOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Breeding" title="Heat">
        A cow seen bulling. Recorded on its own, because the service may not
        happen for hours and the observation is worth keeping either way.
      </PageHeading>
      <RecordEvent<BreedingOptions>
        eyebrow="Breeding"
        title="a heat"
        blurb="Cows the farm may serve."
        pickLabel="Seen bulling"
        emptyPick="No cow is in the servable list."
        load={load}
        animalsOf={(o) => o.animals}
        fieldsOf={(): FieldSpec[] => [
          { name: "event_date", label: "Seen on", kind: "date" },
          { name: "remarks", label: "Notes", kind: "notes",
            placeholder: "Standing to be mounted, clear mucus." },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Record the heat"
        submit={createHeatEvent}
        said={(r, a) => `${a} noted in heat — ${r.name}.`}
      />
    </Page>
  );
}
