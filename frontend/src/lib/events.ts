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

/**
 * A pickable item out of a store, as `common/stock_items.stock_items` answers.
 *
 * `value` is the item code and `label` already carries what is left in store —
 * "Albendazole 10% Oral Drench (1 L) · 1991.93 Litre in store". Rebuilding that
 * sentence on the client would be a second place for the units to go wrong,
 * and feed and drug units are what this app has been burnt by.
 */
export interface StockChoice {
  value: string;
  label: string;
  item_name?: string;
  /** How much is in `warehouse` — never a sum across stores. */
  qty?: number;
  uom?: string;
  /** The store holding the most of it, which is where the issue draws from. */
  warehouse?: string;
  /** Every store holding any, most first, so a short line has somewhere to try. */
  locations?: { warehouse: string; qty: number }[];
}

export interface AnimalChoice {
  name: string;
  label: string;
  herd: string | null;
  herd_label: string | null;
  repro: string | null;
  /* ── only on the narrowed breeding lists ───────────────────────────────
     The server works these out from Livestock Settings — the gestation
     length, the dry-off window, the calving lead — so no screen has to
     hold a second copy of the farm's own rules. */
  /** Her expected calving date. */
  due?: string | null;
  /** Negative means overdue. */
  days_to_calving?: number | null;
  /** Inside the farm's window for this event. Never a refusal: calves come
   *  early, and a screen that would not record one sends people to the desk. */
  ready?: boolean;
  /** Drying off: whether she has already been taken out of milk. */
  dried_off?: boolean;
  /** Heat: her last service is still pending, so this heat is its answer. */
  repeat?: boolean;
}

export interface BreedingOptions {
  animals: AnimalChoice[];
  diagnosis_animals: AnimalChoice[];
  /** Wider than `animals`: a served cow is not servable, but her coming back
   *  into heat is the answer to that service. */
  heat_animals: AnimalChoice[];
  service_types: string[];
  diagnosis_results: string[];
  sires: string[];
  semen_items: StockChoice[];
  default_semen_item: string | null;
  service_wait_days: number;
  employee: string | null;
}

export interface HealthOptions {
  animals: AnimalChoice[];
  /** Cows the farm believes are in calf — the only ones an abortion can
   *  happen to. */
  carrying: AnimalChoice[];
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
  event_types: string[];
  /** Which of them take something out of the drug store. */
  drug_consuming_types: string[];
  drug_items: StockChoice[];
  drug_warehouse: string | null;
  herds: { name: string; label: string; heads: number }[];
  employee: string | null;
}

export interface WeightOptions {
  animals: AnimalChoice[];
  methods: string[];
  herds?: { name: string; label?: string; heads?: number }[];
  employee: string | null;
}

/** A whole group weighed at once: either a platform total to divide by head, or
 *  one figure taken as standing for every animal of that size. */
export interface WeightGroup {
  animals: string[];
  /** The platform read this for all of them together. */
  total_weight_kg?: number;
  /** This weight stands for each of them. */
  weight_kg?: number;
  remarks?: string;
}

export interface WeightRow {
  animal: string;
  weight_kg?: number;
  heart_girth_cm?: number;
  bcs?: number;
}

export interface MovementOptions {
  animals: AnimalChoice[];
  /** In calf, still in milk, inside the farm's dry-off window. */
  dry_off_animals: AnimalChoice[];
  /** In calf, dried off, near her date. */
  calving_animals: AnimalChoice[];
  /** Where this farm dries cows off to (Settings). A suggestion: a different
   *  herd is warned about and then accepted. */
  dry_off_herd: string | null;
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
// createHealthCase is deliberately not wired to a screen. A file is opened
// because somebody is treating her (lib/health.ts: treatAnimal) or because a
// check-up escalated — never as a form of its own, which is how this site ended
// up with a cow carrying three open files for one bout.
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
export interface CalvingDestinations {
  dam: { from_herd: string; to_herd: string; will_move: boolean; reason: string };
  female_calf: { to_herd: string; reason: string };
  male_calf: { to_herd: string; reason: string };
}

export const getCalvingDestinations = (dam: string) =>
  call<CalvingDestinations>(`${NS}.breeding.calving_destinations.calving_destinations`, { dam });
export const recordBirth = (p: Payload) =>
  post<{ name: string; calves: { animal: string }[] }>(`${NS}.breeding.record_birth.record_birth`, p);

/* --------------------------------------------------------- read-only views */

export interface EventRow {
  name: string;
  animal: string | null;
  current_herd: string | null;
  new_herd: string | null;
  event_type: string | null;
  event_date: string | null;
  service_type?: string | null;
}

export interface EventsView {
  rows: EventRow[];
  summary: { total?: number; by_type?: Record<string, number> };
  filters: { types?: string[] };
  error?: string;
}

export interface ProductionRow {
  name: string;
  recording_date: string;
  session?: string | null;
  herd?: string | null;
  cows_milked?: number | null;
  total_yield_kg?: number | null;
  discarded_kg?: number | null;
  net_yield_kg?: number | null;
  milk_revenue?: number | null;
}

export interface ProductionView {
  rows: ProductionRow[];
  summary: Record<string, number>;
  filters: Record<string, unknown>;
  error?: string;
}

export interface ReportsView {
  production: { month_kg?: number; prev_kg?: number; delta_kg?: number; month_rev?: number; prev_rev?: number };
  health: { active_animals?: number; open_cases?: number; cases_month?: number; open_rate?: number };
  reproduction: { pregnant?: number; served?: number; open?: number; births_month?: number; preg_rate?: number };
  herds: { name: string; animals: number }[];
  error?: string;
}

export interface OpenCase {
  value: string;
  label: string;
  animal: string;
}

export interface OpenCasesView {
  cases: OpenCase[];
  drug_items: StockChoice[];
  routes?: string[];
  employee?: string | null;
}

export const getEventsView = () => call<EventsView>(`${NS}.dashboard.get_events.get_events`, {});
export const getProductionView = () =>
  call<ProductionView>(`${NS}.dashboard.get_production.get_production`, {});
export const getReportsView = () => call<ReportsView>(`${NS}.dashboard.get_reports.get_reports`, {});
export const getOpenCases = () =>
  call<OpenCasesView>(`${NS}.health.open_health_cases.open_health_cases`, {});

/* ------------------------------------------------- moving more than one cow */

export interface MoveSuggestion {
  animal: string;
  label: string;
  from_herd: string;
  to_herd: string;
  days_in_herd: number;
  days_expected: number;
  overdue: boolean;
  days_over: number;
  /** Why she is due, in the farm's own terms — "124 days in calf", or the
   *  growth ladder's own wording. */
  reason?: string;
  days_to_calving?: number | null;
}

export interface MovementSuggestions {
  growth: MoveSuggestion[];
  lactation: MoveSuggestion[];
  counts: Record<string, number>;
}

export const getMovementSuggestions = () =>
  call<MovementSuggestions>(`${NS}.movement.movement_suggestions.movement_suggestions`, {});

export const moveAnimals = (p: Payload) =>
  post<{ count: number; herd: string; emptied_from: string[]; heads: number }>(
    `${NS}.movement.move_animals.move_animals`,
    p,
  );

export const recordWeights = (p: Payload) =>
  post<{ count: number; recorded: { animal: string }[]; skipped: { animal: string; why: string }[]; failed: { animal: string; why: string }[] }>(
    `${NS}.weights.record_weights.record_weights`,
    p,
  );
