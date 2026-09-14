import { useCallback } from "react";
import { Page, PageHeading } from "@/components/PageShell";
import { RecordEvent, type FieldSpec } from "@/components/events/RecordEvent";
import {
  createCheckUp,
  createHealthCase,
  createHusbandryEvent,
  createWeightRecord,
  getHealthOptions,
  getHusbandryOptions,
  getWeightOptions,
  type HealthOptions,
  type HusbandryOptions,
  type WeightOptions,
} from "@/lib/events";

/**
 * The health screens.
 *
 * A CHECK UP AND A HEALTH CASE ARE NOT THE SAME THING, and the split is the
 * farm's, not the software's: a check up is one look at one animal on one day,
 * and a case is something followed over time with treatments hung off it. The
 * two doctypes behind them already differ that way; putting them on one screen
 * would make a herdsman choose a data model.
 */

export function CheckUp() {
  const load = useCallback(() => getHealthOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Check up">
        One look at one animal. Vitals if they were taken, what was done, and
        whether it needs another look.
      </PageHeading>
      <RecordEvent<HealthOptions>
        eyebrow="Health"
        title="a check up"
        blurb="Any animal on the farm."
        pickLabel="Which animal"
        emptyPick="No animals on this site."
        load={load}
        animalsOf={(o) => o.animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "event_date", label: "Seen on", kind: "date" },
          { name: "reason_for_check", label: "Why she was looked at", kind: "text",
            placeholder: "Off her feed since yesterday", required: true },
          { name: "temperature_c", label: "Temperature (°C)", kind: "number", step: "0.1" },
          { name: "heart_rate", label: "Heart rate", kind: "number" },
          { name: "respiration_rate", label: "Respiration", kind: "number" },
          { name: "bcs", label: "Body condition", kind: "number", step: "0.25",
            hint: "1 to 5." },
          { name: "lameness_score", label: "Lameness", kind: "number",
            hint: "0 to 5, 0 being sound." },
          { name: "appearance", label: "Appearance", kind: "select", options: o.appearances },
          { name: "hydration", label: "Hydration", kind: "select", options: o.hydrations },
          { name: "suggested_disease", label: "Suspected", kind: "select", options: o.diseases },
          { name: "action_taken", label: "What was done", kind: "select", options: o.actions },
          { name: "follow_up_date", label: "Look again on", kind: "date" },
          { name: "action_notes", label: "Notes", kind: "notes" },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Record the check up"
        submit={createCheckUp}
        said={(r, a) => `${a} seen — ${r.name}.`}
      />
    </Page>
  );
}

export function HealthCase() {
  const load = useCallback(() => getHealthOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Health case">
        Something followed over time rather than settled in one visit.
        Treatments are added to the case as they happen, so the whole course is
        one record.
      </PageHeading>
      <RecordEvent<HealthOptions>
        eyebrow="Health"
        title="a case"
        blurb="Any animal on the farm."
        pickLabel="Which animal"
        emptyPick="No animals on this site."
        load={load}
        animalsOf={(o) => o.animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "event_date", label: "Opened on", kind: "date" },
          { name: "presenting_symptoms", label: "What is wrong", kind: "text",
            placeholder: "Swollen left hind quarter, hard", required: true },
          { name: "provisional_diagnosis", label: "Provisionally", kind: "select",
            options: o.diseases },
          { name: "severity", label: "How bad", kind: "select", options: o.severities },
          { name: "case_status", label: "Status", kind: "select", options: o.case_statuses },
          { name: "vet_name", label: "Vet, if called", kind: "text",
            hint: "Leaving this blank records that none was." },
          { name: "body_systems", label: "Affecting", kind: "text",
            placeholder: "Udder" },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Open the case"
        submit={createHealthCase}
        said={(r, a) => `Case open for ${a} — ${r.name}. Add treatments to it as they happen.`}
      />
    </Page>
  );
}

export function Weight() {
  const load = useCallback(() => getWeightOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Weight">
        What an animal weighs, and how it was arrived at — a scale and a girth
        tape are not the same number and the record says which.
      </PageHeading>
      <RecordEvent<WeightOptions>
        eyebrow="Health"
        title="a weight"
        blurb="Any animal on the farm."
        pickLabel="Which animal"
        emptyPick="No animals on this site."
        load={load}
        animalsOf={(o) => o.animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "event_date", label: "Weighed on", kind: "date" },
          { name: "method", label: "How", kind: "select", options: o.methods, required: true },
          { name: "weight_kg", label: "Weight (kg)", kind: "number", step: "0.1" },
          { name: "heart_girth_cm", label: "Heart girth (cm)", kind: "number", step: "0.1",
            hint: "The weight is worked out from this if none is given." },
          { name: "bcs", label: "Body condition", kind: "number", step: "0.25" },
          { name: "remarks", label: "Notes", kind: "notes" },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Record the weight"
        submit={createWeightRecord}
        said={(r, a) => `${a} weighed — ${r.name}.`}
      />
    </Page>
  );
}

export function Husbandry() {
  const load = useCallback(() => getHusbandryOptions(), []);
  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Husbandry">
        The routine jobs — dosing, dipping, trimming, dehorning. Anything that
        uses a drug takes it out of the store as it is recorded.
      </PageHeading>
      <RecordEvent<HusbandryOptions>
        eyebrow="Health"
        title="a husbandry job"
        blurb="Any animal on the farm."
        pickLabel="Which animal"
        emptyPick="No animals on this site."
        load={load}
        animalsOf={(o) => o.animals}
        fieldsOf={(o): FieldSpec[] => [
          { name: "event_date", label: "Done on", kind: "date" },
          {
            name: "event_type",
            label: "What was done",
            kind: "select",
            options: (o.event_types as string[]) || [
              "Vaccination", "Deworming", "Hoof Trimming", "Dehorning",
            ],
            required: true,
          },
          { name: "remarks", label: "Notes", kind: "notes" },
        ]}
        operatorOf={(o) => o.employee}
        submitLabel="Record it"
        submit={createHusbandryEvent}
        said={(r, a) => `Recorded for ${a} — ${r.name}.`}
      />
    </Page>
  );
}
