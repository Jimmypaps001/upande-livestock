import { useCallback } from "react";
import { Page, PageHeading } from "@/components/PageShell";
import { RecordEvent, type FieldSpec } from "@/components/events/RecordEvent";
import {
  createCheckUp,
  createHealthCase,
  getHealthOptions,
  type HealthOptions,
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
        // A CHECK-UP IS WHERE A FILE COMES FROM, so the answer says whether one
        // was opened. Escalating used to be a word in a dropdown and nothing
        // else happened; now the file exists and the herdsman is told its name.
        said={(r, a) => {
          if (r.case_opened) {
            return `${a} seen — ${r.name}. A health file is open for her: ${r.case}.`;
          }
          if (r.case) {
            return `${a} seen — ${r.name}. Added to her open file ${r.case}.`;
          }
          if (r.suggest_case) {
            return `${a} seen — ${r.name}. She was treated but has no file open; open one on the Treatment screen if this is more than a one-off.`;
          }
          return `${a} seen — ${r.name}.`;
        }}
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
