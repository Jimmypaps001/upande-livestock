/**
 * The record-an-event screens: breeding, health, husbandry, movement, weight.
 *
 * Every one of them is the same shape — pick an animal the farm may actually
 * do this to, fill in a few fields, submit — and they differ only in which
 * animals are offered and which fields those are. So they share a scaffold,
 * and this file is the part that differs: what each screen asks the server for
 * and what it sends back.
 *
 * THE ANIMAL LIST IS THE SERVER'S, NEVER "every active animal". A weaner in
 * the service list is an invitation to record a service biology rules out, and
 * a cow with no open service in the diagnosis list is a "Confirmed" invented
 * from nothing — which then drives calving, herd moves and milk. Each options
 * endpoint already narrows; the screens ask and do not filter for themselves.
 */
import { call, type Envelope } from "@/lib/frappe";

const NS = "upande_livestock.serverscripts";

export interface AnimalChoice {
  name: string;
  label: string;
  herd: string | null;
  herd_label: string | null;
  repro: string | null;
}

export interface BreedingOptions {
  animals: AnimalChoice[];
  diagnosis_animals: AnimalChoice[];
  service_types: string[];
  diagnosis_results: string[];
  sires: string[];
  semen_items: { item_code: string; item_name?: string; qty?: number }[];
  default_semen_item: string | null;
  service_wait_days: number;
  employee: string | null;
}

export interface HealthOptions {
  animals: AnimalChoice[];
  diseases: string[];
  abortion_causes: string[];
  appearances: string[];
  hydrations: string[];
  actions: string[];
  case_statuses: string[];
  severities: string[];
  routes: string[];
  employee: string | null;
}

export interface HusbandryOptions {
  animals: AnimalChoice[];
  /** The routine jobs this farm records. Server-supplied, because a farm that
   *  adds "Dipping" should see it without a frontend release. */
  event_types?: string[];
  employee: string | null;
  [key: string]: unknown;
}

export interface WeightOptions {
  animals: AnimalChoice[];
  methods: string[];
  employee: string | null;
}

export interface MovementOptions {
  animals: AnimalChoice[];
  herds: { name: string; label: string }[];
  calving_outcomes: string[];
  employee: string | null;
}

export const getBreedingOptions = () =>
  call<BreedingOptions>(`${NS}.breeding.breeding_options.breeding_options`, {});
export const getHealthOptions = () =>
  call<HealthOptions>(`${NS}.health.health_options.health_options`, {});
export const getHusbandryOptions = () =>
  call<HusbandryOptions>(`${NS}.husbandry.husbandry_options.husbandry_options`, {});
export const getWeightOptions = () =>
  call<WeightOptions>(`${NS}.weights.weight_options.weight_options`, {});
export const getMovementOptions = () =>
  call<MovementOptions>(`${NS}.movement.event_options.event_options`, {});

type Payload = Record<string, unknown>;
const post = <T>(method: string, payload: Payload): Promise<Envelope<T>> =>
  call<T>(method, { payload });

export const createServiceEvent = (p: Payload) =>
  post<{ name: string }>(`${NS}.breeding.create_service_event.create_service_event`, p);
export const createPregnancyDiagnosis = (p: Payload) =>
  post<{ name: string }>(`${NS}.breeding.create_pregnancy_diagnosis.create_pregnancy_diagnosis`, p);
export const createAbortionEvent = (p: Payload) =>
  post<{ name: string }>(`${NS}.breeding.create_abortion_event.create_abortion_event`, p);
export const createDryingOffEvent = (p: Payload) =>
  post<{ name: string }>(`${NS}.breeding.create_drying_off_event.create_drying_off_event`, p);
export const createHeatEvent = (p: Payload) =>
  post<{ name: string }>(`${NS}.breeding.create_heat_event.create_heat_event`, p);
export const createCheckUp = (p: Payload) =>
  post<{ name: string }>(`${NS}.health.create_check_up.create_check_up`, p);
export const createHealthCase = (p: Payload) =>
  post<{ name: string }>(`${NS}.health.create_health_case.create_health_case`, p);
export const addCaseTreatment = (p: Payload) =>
  post<{ name: string }>(`${NS}.health.add_case_treatment.add_case_treatment`, p);
export const createHusbandryEvent = (p: Payload) =>
  post<{ name: string }>(`${NS}.husbandry.create_husbandry_event.create_husbandry_event`, p);
export const createWeightRecord = (p: Payload) =>
  post<{ name: string }>(`${NS}.weights.create_weight_record.create_weight_record`, p);
export const createMovementEvent = (p: Payload) =>
  post<{ name: string }>(`${NS}.movement.create_movement_event.create_movement_event`, p);
export const getOpenHealthCases = () =>
  call<{ cases: Record<string, unknown>[] }>(`${NS}.health.open_health_cases.open_health_cases`, {});
export const getCalvingDestinations = (dam: string) =>
  call<{
    dam: { from_herd: string; to_herd: string; will_move: boolean; reason: string };
    female_calf: { to_herd: string; reason: string };
    male_calf: { to_herd: string; reason: string };
  }>(`${NS}.breeding.calving_destinations.calving_destinations`, { dam });
export const recordBirth = (p: Payload) =>
  post<{ name: string; calves: { animal: string }[] }>(`${NS}.breeding.record_birth.record_birth`, p);
