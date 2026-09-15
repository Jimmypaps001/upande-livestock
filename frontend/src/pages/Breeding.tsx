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
 * Each is the same scaffold with a DIFFERENT ANIMAL LIST, and the list is the
 * whole point. The server decides who may be served (past the post-calving
 * wait, on the right rung of the ladder), who may be diagnosed (an open service
 * to answer), who may be dried off (in calf, in milk, near her date), who may
 * lose a pregnancy (carrying one), and who is worth recording a heat on (old
 * enough, not in calf — including the served cow whose heat means the service
 * failed).
 *
 * THE NARROWING IS NOT COSMETIC. A "Confirmed" invented for a cow nobody served
 * drives calving, herd moves and months of feed. A drying off recorded against
 * a cow who is not carrying takes her out of milk and out of her herd's ration.
 * The cheapest place to prevent any of it is the list the screen offers.
 *
 * And every threshold behind those lists is read from Livestock Settings, never
 * written down here — the farm moves its dry-off window on the Settings page
 * and these screens move with it.
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
            options: o.semen_items.map((i) => i.value),
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
        blurb="Cows the farm believes are in calf."
        pickLabel="Which cow"
        // ONLY WHO CAN ACTUALLY LOSE ONE. An abortion is recorded against the
        // pregnancy it ends; offering the whole herd invited a record against a
        // cow with nothing to end, which the server refuses after the herdsman
        // has already filled the form in.
        emptyPick="No cow is carrying. An abortion is recorded against a confirmed pregnancy, so there is nothing to record against yet."
        load={load}
        animalsOf={(o) => o.carrying}
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
        Taking a cow out of milk before she calves. Only cows the farm believes
        are in calf and still milking are offered — drying off a cow who is not
        carrying throws away a lactation for nothing.
      </PageHeading>
      <RecordEvent<MovementOptions>
        eyebrow="Breeding"
        title="a drying off"
        blurb="In calf, still in milk, and near enough her date."
        pickLabel="Which cow"
        // THE WINDOW IS THE FARM'S, from Livestock Settings — the dry days a
        // heifer gets arriving at Steamers, and the ones a cow gets coming off
        // the low-yield herd. Nothing about it is decided in this file.
        emptyPick="No cow is due to be dried off. Either none is confirmed in calf, or none is close enough to calving yet."
        load={load}
        animalsOf={(o) => o.dry_off_animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "event_date", label: "Dried off on", kind: "date" },
          // The farm sets where dry cows go; the screen offers it rather than
          // making somebody find it, and says something when it is changed.
          // Never refuses: a cow goes to a different pen for reasons this app
          // does not know, and refusing would send the herdsman to the desk.
          { name: "new_herd", label: "Moving to", kind: "select",
            options: o.herds.map((h) => h.name),
            value: o.dry_off_herd || undefined,
            hint: o.dry_off_herd
              ? `${o.dry_off_herd} is where this farm dries cows off to.`
              : "No drying-off herd is set — Settings, Herd Movement.",
            warnIfChanged: o.dry_off_herd
              ? `Not ${o.dry_off_herd}, where this farm dries cows off to. It will be recorded as it stands.`
              : undefined },
          { name: "remarks", label: "Notes", kind: "notes" },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Dry her off"
        submit={createDryingOffEvent}
        // The server repeats the deviation it recorded, so the confirmation
        // says where she actually went rather than only that it worked.
        said={(r, a) =>
          `${a} is dry — ${r.name}.` +
          (r.new_herd ? ` She is in ${r.new_herd}.` : "") +
          (r.note ? ` ${r.note}` : "")
        }
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
        blurb="Old enough to serve, and not already in calf."
        pickLabel="Seen bulling"
        // WIDER THAN THE SERVICE LIST, deliberately. A cow served three weeks
        // ago is not servable — but her coming back into heat IS the answer to
        // that service, and it is the farm finding out the insemination failed
        // weeks before the pregnancy check would have said so. The old screen
        // offered the servable list, which excludes her the moment she is
        // served, and so lost every repeat.
        emptyPick="No cow is old enough to serve, or they are all in calf."
        load={load}
        animalsOf={(o) => o.heat_animals}
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
