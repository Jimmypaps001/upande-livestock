/**
 * The health file and everything that hangs off it.
 *
 * Kept apart from lib/events.ts on purpose. Those are one-shot recordings — a
 * weight, a heat, a dose — and this is a record with a life: it is opened by
 * something, written in over days, and closed with an ending. The two have
 * nothing in common but the word "health".
 */
import { call, type Envelope } from "@/lib/frappe";

const NS = "upande_livestock.serverscripts.health";
type Payload = Record<string, unknown>;
const post = <T>(method: string, payload: Payload): Promise<Envelope<T>> =>
  call<T>(method, { payload });

/** A case still being written in. The server owns this list; see health_case.py. */
export const OPEN_STATUSES = ["Open", "Under Treatment"] as const;
/** The four ways a file ends. */
export const CLOSED_STATUSES = ["Recovered", "Chronic", "Died", "Culled"] as const;
export type CaseStatus = (typeof OPEN_STATUSES)[number] | (typeof CLOSED_STATUSES)[number];

export interface Concern {
  kind: "long" | "stale" | "untreated";
  days: number;
  says: string;
}

export interface CaseRow {
  name: string;
  animal: string;
  animal_name: string | null;
  current_herd: string | null;
  case_status: CaseStatus;
  opened_date: string | null;
  closed_date: string | null;
  presenting_symptoms: string | null;
  provisional_diagnosis: string | null;
  confirmed_diagnosis: string | null;
  severity: string | null;
  duration_days: number | null;
  production_loss_kg: number | null;
  total_treatment_cost: number | null;
  vet_called: number | null;
  vet_name: string | null;
  days_open: number | null;
  treatments: number;
  last_treatment_on: string | null;
  last_response: string | null;
  open: boolean;
  concern: Concern | null;
}

export interface CaseRegister {
  from: string;
  to: string;
  cases: CaseRow[];
  counts: {
    total: number;
    open: number;
    closed: number;
    recovered: number;
    died: number;
    lost_kg: number;
    cost: number;
  };
  truncated: boolean;
  concern_days: number;
  stale_days: number;
  months: string[];
}

export interface CaseEntry {
  name: string;
  on: string | null;
  /** Day 1 is the day the file was opened. A course is read in days. */
  day: number | null;
  time: string | null;
  drug: string | null;
  drug_item: string | null;
  qty: number;
  dosage: string | null;
  route: string | null;
  withdrawal_days: number | null;
  by: string | null;
  response: string | null;
  /** -1 worse, 0 no change, 1 improving, 2 resolved, null not assessed. */
  trend: number | null;
  cost: number;
  issued: string | null;
  notes: string | null;
}

export interface CaseFile {
  case: CaseRow & {
    animal_name: string;
    herd: string | null;
    opened_by: string | null;
    body_systems: string | null;
    vet_visit_date: string | null;
    milk_safe_date: string | null;
    treatment_cost: number;
    outcome_notes: string | null;
    linked_disposal: string | null;
  };
  entries: CaseEntry[];
  drugs: { drug: string; qty: number; times: number; uom: string | null }[];
  verdict: { reads: string; says: string };
  concern_days: number;
  stale_days: number;
  others: {
    name: string;
    opened_date: string | null;
    closed_date: string | null;
    case_status: CaseStatus;
    provisional_diagnosis: string | null;
  }[];
}

export interface AnimalCaseStanding {
  animal: string;
  open_case:
    | (CaseRow & { days_open: number | null; treatments: number })
    | null;
  history: {
    name: string;
    opened_date: string | null;
    closed_date: string | null;
    case_status: CaseStatus;
    presenting_symptoms: string | null;
    provisional_diagnosis: string | null;
    duration_days: number | null;
  }[];
  closed_count: number;
}

export interface WardCase {
  name: string;
  animal: string;
  animal_name: string | null;
  current_herd: string | null;
  case_status: CaseStatus;
  opened_date: string | null;
  severity: string | null;
  provisional_diagnosis: string | null;
  days_open: number | null;
  last_treatment_on: string | null;
  concern: Concern | null;
}

export interface HealthOverview {
  since: string;
  herd_size: number;
  under_treatment: number;
  share: number | null;
  ward: WardCase[];
  worrying: WardCase[];
  months: { month: string; opened: number; closed: number }[];
  diagnoses: { diagnosis: string | null; cases: number; confirmed: number; open: number }[];
  severity: { severity: string | null; cases: number }[];
  herds: { herd: string | null; cases: number; open: number }[];
  cost: { treatment: number; lost_kg: number; costed: number; cases: number };
  concern_days: number;
  stale_days: number;
}

export interface TreatmentLine {
  drug_item?: string;
  drug_name_text?: string;
  qty?: number;
  dosage?: string;
  route?: string;
  withdrawal_period_days?: number;
  response_observed?: string;
  administered_by?: string;
  notes?: string;
}

export const getHealthOverview = () =>
  call<HealthOverview>(`${NS}.health_overview.health_overview`, { payload: {} });

export const getHealthCases = (p: Payload = {}) =>
  call<CaseRegister>(`${NS}.health_cases.health_cases`, { payload: p });

export const getCaseFile = (name: string) =>
  call<CaseFile>(`${NS}.health_case_file.health_case_file`, { payload: { case: name } });

export const getAnimalCase = (animal: string) =>
  call<AnimalCaseStanding>(`${NS}.case_for_animal.case_for_animal`, { payload: { animal } });

export const treatAnimal = (p: Payload) =>
  post<{
    case: string;
    animal: string;
    opened: boolean;
    case_status: CaseStatus;
    added: number;
    treatments: number;
    stock_entry: string;
  }>(`${NS}.treat_animal.treat_animal`, p);

export const closeCase = (p: Payload) =>
  post<{
    case: string;
    animal: string;
    case_status: CaseStatus;
    closed_date: string;
    duration_days: number | null;
  }>(`${NS}.close_health_case.close_health_case`, p);
