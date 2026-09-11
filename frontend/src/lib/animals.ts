/**
 * What the Animals page needs to know about an animal.
 *
 * Shapes first, data later. Every field here maps onto something the server
 * already holds — Animal, Livestock Event, Milk Recording — so wiring this up
 * is a matter of filling these in rather than redesigning the page around what
 * the endpoints happen to return. The sample below is real Kaitet register
 * numbers and real herd names, because a layout tested on "Animal 1 / Herd A"
 * looks fine until the day it meets "12 MONTHS-SERVICE (BULLYING HEIFERS)".
 */

/** Where a cow stands in the loop between one calving and the next. */
export type CycleStage =
  | "fresh"      // calved, inside the voluntary wait
  | "open"       // eligible to serve, not yet in calf
  | "served"     // inseminated, awaiting the check
  | "confirmed"  // carrying
  | "dry"        // dried off, steaming up
  | "heifer"     // never calved
  | "retired";   // left the herd

export interface CycleState {
  stage: CycleStage;
  /** Days since the event that started this stage. */
  dayInStage: number;
  /** Days since her last calving — the number that drives everything else. */
  daysInMilk: number | null;
  /** What the farm should be watching for next, in the farm's own words. */
  nextUp: string;
  /** When that is expected. Null when nothing is pending. */
  nextOn: string | null;
}

export type MilestoneKind =
  | "birth"
  | "movement"
  | "service"
  | "confirmed"
  | "calving"
  | "abortion"
  | "drying"
  | "health"
  | "weight";

export interface Milestone {
  kind: MilestoneKind;
  on: string;
  label: string;
  detail?: string;
}

/** A stretch of her life spent in one herd — the bands under the timeline. */
export interface HerdSpell {
  herd: string;
  from: string;
  /** Null means "still there". */
  to: string | null;
}

export interface AnimalKpis {
  parity: number;
  services: number;
  conceptions: number;
  abortions: number;
  /** Conceptions over services, as a percentage. Null before her first service. */
  conceptionRate: number | null;
  /** Mean days between calvings. Null until she has calved twice. */
  calvingInterval: number | null;
  /** Kilograms in her current or most recent lactation. */
  lactationYield: number | null;
  /** Her yield as a percentage of the herd's median. 100 is the median cow. */
  yieldIndex: number | null;
  /** Treatments in the last twelve months. */
  treatments: number;
}

export interface AnimalSummary {
  id: string;
  name: string;
  sex: "Female" | "Male";
  herd: string;
  breed: string | null;
  bornOn: string | null;
  status: string;
  stage: CycleStage;
  photo: string | null;
}

export interface AnimalProfile extends AnimalSummary {
  dam: string | null;
  sire: string | null;
  lastCalving: string | null;
  expectedCalving: string | null;
  cycle: CycleState;
  kpis: AnimalKpis;
  milestones: Milestone[];
  spells: HerdSpell[];
}

/** How each stage reads on screen, and the arc it owns on the cycle ring. */
export const STAGES: Record<
  CycleStage,
  { label: string; note: string; tone: string }
> = {
  heifer: { label: "Heifer", note: "not yet calved", tone: "var(--sd-data-indigo)" },
  fresh: { label: "Fresh", note: "just calved", tone: "var(--sd-data-cyan)" },
  open: { label: "Open", note: "ready to serve", tone: "var(--sd-data-amber)" },
  served: { label: "Served", note: "awaiting the check", tone: "var(--sd-data-purple)" },
  confirmed: { label: "In calf", note: "carrying", tone: "var(--sd-data-green)" },
  dry: { label: "Dry", note: "steaming up", tone: "var(--sd-data-pink)" },
  retired: { label: "Left the herd", note: "no longer on the farm", tone: "var(--sd-quiet)" },
};

/** The loop, in the order a cow travels it. `retired` and `heifer` sit outside. */
export const CYCLE_ORDER: CycleStage[] = ["fresh", "open", "served", "confirmed", "dry"];

export const MILESTONE_TONE: Record<MilestoneKind, string> = {
  birth: "var(--sd-data-indigo)",
  movement: "var(--sd-quiet)",
  service: "var(--sd-data-purple)",
  confirmed: "var(--sd-data-green)",
  calving: "var(--sd-data-cyan)",
  abortion: "var(--sd-data-red)",
  drying: "var(--sd-data-pink)",
  health: "var(--sd-data-amber)",
  weight: "var(--sd-muted)",
};

/** Age as a farm says it: "7y 2m", "14m", "3w". */
export function ageFrom(bornOn: string | null, now = new Date()): string {
  if (!bornOn) return "—";
  const b = new Date(bornOn);
  if (Number.isNaN(b.getTime())) return "—";
  const days = Math.max(0, Math.round((now.getTime() - b.getTime()) / 86400000));
  if (days < 21) return `${days}d`;
  if (days < 90) return `${Math.round(days / 7)}w`;
  const months = Math.round(days / 30.44);
  if (months < 24) return `${months}m`;
  return `${Math.floor(months / 12)}y ${months % 12}m`;
}

export function daysBetween(from: string, to: string | null, now = new Date()): number {
  const a = new Date(from).getTime();
  const b = to ? new Date(to).getTime() : now.getTime();
  return Math.max(0, Math.round((b - a) / 86400000));
}
