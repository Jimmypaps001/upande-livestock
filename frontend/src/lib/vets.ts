import { useEffect, useState } from "react";
import { call, isError, type Envelope } from "@/lib/frappe";

const VET_OPTIONS = "upande_livestock.serverscripts.people.vet_options.vet_options";

export interface VetChoice {
  value: string;
  label: string;
  /** Internal (a farm employee) or External (a visiting practitioner). */
  type: "Internal" | "External";
  detail: string;
}

export interface VetOptions {
  vets: VetChoice[];
  /** The Livestock Vet record of whoever is signed in, or null. */
  mine: string | null;
}

/** Enabled vets, and the signed-in user's own. */
export function getVetOptions(): Promise<Envelope<VetOptions>> {
  return call<VetOptions>(VET_OPTIONS, { payload: {} });
}

/**
 * The vets a record may name. Loaded once per mount; the picker starts on the
 * signed-in user's own vet record when they have one, and the server applies the
 * same default when none is sent.
 */
export function useVets() {
  const [vets, setVets] = useState<VetChoice[]>([]);
  const [mine, setMine] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let live = true;
    void getVetOptions().then((r) => {
      if (!live) return;
      if (!isError(r)) {
        setVets(r.vets ?? []);
        setMine(r.mine ?? null);
      }
      setLoaded(true);
    });
    return () => {
      live = false;
    };
  }, []);

  return { vets, mine, loaded };
}

/** `useVets` plus the chosen vet, started on the signed-in user's own record
 *  and never overwritten once somebody has chosen. */
export function useVetChoice() {
  const { vets, mine, loaded } = useVets();
  // null until somebody chooses; "" is a deliberate "no vet".
  const [picked, setVet] = useState<string | null>(null);
  const vet = picked ?? mine ?? "";
  return { vets, vet, setVet, loaded };
}

// ---- The Vets screen: KPIs per vet, and adding one ------------------------

const VETS_LIST = "upande_livestock.serverscripts.people.vets_list.vets_list";
const ADD_VET = "upande_livestock.serverscripts.people.add_vet.add_vet";

export const VET_PERIODS = [
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "month", label: "This month" },
  { value: "year", label: "This year" },
  { value: "12m", label: "Last 12 months" },
] as const;
export type VetPeriod = (typeof VET_PERIODS)[number]["value"];

export interface VetKpis {
  cases_opened: number;
  cases_closed: number;
  cases_open_now: number;
  treatments: number;
  check_ups: number;
  inseminations: number;
  pds_done: number;
  services_confirmed: number;
  services_pending: number;
  /** Percent of services confirmed in calf; null with no services. */
  pregnancy_rate: number | null;
  avg_days_to_close: number | null;
  drug_cost: number;
  last_activity: string | null;
}

export interface VetRow extends VetChoice {
  vet: string;
  vet_name: string;
  enabled: number;
  initials: string;
  image: string;
  phone: string;
  email: string;
  employee: string;
  supplier: string;
  practice_name: string;
  registration_number: string;
  qualification: string;
  licence_expiry: string | null;
  licence_expired: boolean;
  kpis: VetKpis;
}

export interface VetsList {
  period: VetPeriod | null;
  from: string;
  to: string;
  vets: VetRow[];
}

/** Every vet with their KPIs for a named period. */
export function getVetsList(period: VetPeriod = "90d"): Promise<Envelope<VetsList>> {
  return call<VetsList>(VETS_LIST, { payload: { period } });
}

/** What the ERP form takes; the same payload the phone sends. */
export interface NewVet {
  vet_type: "Internal" | "External";
  employee?: string;
  vet_name?: string;
  phone?: string;
  email?: string;
  registration_number?: string;
  qualification?: string;
  licence_expiry?: string;
  practice_name?: string;
  supplier?: string;
}

export function addVet(vet: NewVet): Promise<Envelope<{ vet: VetChoice }>> {
  return call<{ vet: VetChoice }>(ADD_VET, { payload: vet });
}

/** The mandatory fields by type, mirroring the Livestock Vet controller. The
 *  server re-checks; this only spares a round trip. Returns the first problem. */
export function vetProblem(v: NewVet): string | null {
  const blank = (s?: string) => !(s || "").trim();
  if (v.vet_type === "Internal") {
    return blank(v.employee) ? "An internal vet is an employee. Choose the Employee." : null;
  }
  if (blank(v.vet_name)) return "Vet Name is required for an external vet.";
  if (blank(v.registration_number)) return "Kenya Veterinary Board Registration No. is required for an external vet.";
  if (blank(v.phone)) return "Phone is required for an external vet.";
  return null;
}
