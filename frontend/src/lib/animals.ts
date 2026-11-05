/**
 * What the Animals page needs to know about an animal.
 *
 * Shapes first, data later. Every field here maps onto something the server
 * already holds — Animal, Livestock Event — so wiring this up
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
  | "heifer"     // never calved
  | "calf"       // young, not yet weaned (either sex)
  | "weaner" | "grower" | "finisher" | "market"  // a male's liveweight ladder
  | "steer"      // a male past weaning with no weighing yet
  | "bull"       // a male in the breeding stream
  | "unknown"    // sex not recorded: no cycle is drawn
  | "retired";   // left the herd

/** Which cycle the server chose for the animal: its sex decides. */
export type CycleKind = "repro" | "growth" | "bull" | "unknown" | "retired";

export interface GrowthState {
  kg: number;
  stage: CycleStage;
  fromKg: number;
  nextStage: CycleStage | null;
  nextKg: number | null;
  /** How far through the current band, 0-100. */
  pct: number;
  /** kg/day, null until two weighings exist. */
  adg: number | null;
  daysToNext: number | null;
  /** Null when the move into the Fattening herd was never recorded. */
  daysOnFeed: number | null;
  weighedOn: string | null;
}

export interface BullState {
  state: "At rest" | "In breeding cycle";
  lastService: string | null;
  reason: string;
}

export interface CycleState {
  /** Absent on older servers: read as "repro". */
  kind?: CycleKind;
  stage: CycleStage;
  /** Breeding bull / Young bull. */
  class?: string;
  growth?: GrowthState | null;
  bull?: BullState;
  /** Days since the event that started this stage. */
  dayInStage: number;
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
  /** ~240 px list thumbnail of `photo`; lists use it, only the portrait loads `photo`. */
  thumb?: string | null;
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
  gain?: { lifetime_adg: number | null; herd_adg: number | null; target_adg_kg: number | null };
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
  calf: { label: "Calf", note: "on the dam", tone: "var(--sd-data-cyan)" },
  weaner: { label: "Weaner", note: "weaned, building frame", tone: "var(--sd-data-indigo)" },
  grower: { label: "Grower", note: "growing out", tone: "var(--sd-data-purple)" },
  finisher: { label: "Finisher", note: "on finishing feed", tone: "var(--sd-data-amber)" },
  market: { label: "Market-ready", note: "at sale weight", tone: "var(--sd-data-green)" },
  steer: { label: "Young male", note: "not yet weighed", tone: "var(--sd-data-purple)" },
  bull: { label: "Breeding bull", note: "kept for breeding", tone: "var(--sd-data-red)" },
  unknown: { label: "Unknown", note: "sex not recorded", tone: "var(--sd-quiet)" },
  retired: { label: "Left the herd", note: "no longer on the farm", tone: "var(--sd-quiet)" },
};

/** The loop, in the order a cow travels it. `retired` and `heifer` sit outside. */
export const CYCLE_ORDER: CycleStage[] = ["fresh", "open", "served", "confirmed"];

/** A male's liveweight ladder, lowest first. */
export const GROWTH_ORDER: CycleStage[] = ["calf", "weaner", "grower", "finisher", "market"];

/** The cycle the animal is on, defaulting to the reproductive one for older servers. */
export function cycleKind(cycle: CycleState): CycleKind {
  return cycle.kind ?? "repro";
}

export type PlaceholderKind = "bull" | "steer" | "calf" | "heifer" | "cow";

/** Which generic picture stands in for an animal with no photograph: sex AND stage. */
export function placeholderKind(sex: string | null | undefined, stage: CycleStage): PlaceholderKind {
  if (stage === "calf") return "calf";
  if (sex === "Male") return stage === "bull" ? "bull" : "steer";
  if (stage === "heifer") return "heifer";
  if (sex === "Female") return "cow";
  return "steer";
}

export const MILESTONE_TONE: Record<MilestoneKind, string> = {
  birth: "var(--sd-data-indigo)",
  movement: "var(--sd-quiet)",
  service: "var(--sd-data-purple)",
  confirmed: "var(--sd-data-green)",
  calving: "var(--sd-data-cyan)",
  abortion: "var(--sd-data-red)",
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

/** Two letters to stand in for a photograph.
 *
 *  Her name first, because that is what the farm calls her; the register
 *  number only when she has no name of her own, which is every bull calf —
 *  "B013/26" has no initials, so the digits are what identifies him. */
export function initialsOf(name: string, id: string): string {
  const words = (name || "").trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  const single = words[0] || "";
  if (single && !/^[AB]\d{3}\//i.test(single)) return single.slice(0, 2).toUpperCase();
  const parsed = parse(id);
  return parsed ? String(parsed.seq).padStart(3, "0").slice(-2) : (id || "?").slice(0, 2).toUpperCase();
}

/** The three parts of a register number, or null. Kept here so initialsOf can
 *  fall back on the sequence without the page importing a parser. */
function parse(id: string): { prefix: string; seq: number; yy: number } | null {
  const m = /^([AB])(\d{3})\/(\d{2})$/.exec((id || "").trim().toUpperCase());
  return m ? { prefix: m[1], seq: Number(m[2]), yy: Number(m[3]) } : null;
}
