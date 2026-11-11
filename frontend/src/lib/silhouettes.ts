import type { CycleStage } from "@/lib/animals";

/**
 * Which drawing stands in for an animal with no photograph.
 *
 * Two steps. First the CLASS, from what the farm knows about the animal:
 * species, then age, then sex and stage.
 * Then the POSE within that class (standing, turned, grazing), chosen from
 * the animal's own number, so a list of photo-less animals is not one picture
 * repeated, and the same animal always gets the same picture on every screen
 * and every visit.
 *
 * The drawings themselves are in upande_livestock/public/images/silhouettes/
 * (the supplied artwork, traced by scripts/trace_silhouettes.py); this file
 * only names them.
 */

export type SilhouetteClass = "cow" | "heifer" | "bull" | "steer" | "calf" | "sheep" | "goat";

export type Silhouette =
  | "cow" | "cow-udder" | "cow-grazing" | "cow-grazing-2"
  | "heifer"
  | "bull"
  | "steer" | "steer-turned" | "steer-grazing"
  | "calf" | "calf-grazing";

/**
 * The poses each class is drawn in, from the traced artwork (the first is the
 * plain standing one). A heifer shares the grazing cow that shows no udder.
 * There is no sheep or goat artwork, so for now they fall back to the calf —
 * the smallest animal of the set — until drawings of their own are supplied.
 */
export const POSES: Record<SilhouetteClass, readonly Silhouette[]> = {
  cow: ["cow", "cow-udder", "cow-grazing-2", "cow-grazing"],
  heifer: ["heifer", "cow-grazing"],
  bull: ["bull"],
  steer: ["steer", "steer-turned", "steer-grazing"],
  calf: ["calf", "calf-grazing"],
  sheep: ["calf", "calf-grazing"],
  goat: ["calf", "calf-grazing"],
};

/** What the pick reads. Every field but the number may be missing. */
export interface SilhouetteSubject {
  id: string;
  sex?: string | null;
  stage?: CycleStage | null;
  species?: string | null;
  bornOn?: string | null;
}

/** Younger than this and it is drawn as a calf, whatever its stage says. */
export const CALF_DAYS = 210;
/** A female younger than this, whose stage does not say she has calved, is a heifer. */
export const HEIFER_DAYS = 730;

/** Stages that mean she has calved: a cow. */
const CALVED: CycleStage[] = ["fresh", "served", "confirmed"];

function ageDays(bornOn: string | null | undefined, now: Date): number | null {
  if (!bornOn) return null;
  const t = new Date(bornOn).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((now.getTime() - t) / 86400000));
}

export function silhouetteClass(a: Omit<SilhouetteSubject, "id">, now = new Date()): SilhouetteClass {
  const species = (a.species || "").toLowerCase();
  if (species === "sheep") return "sheep";
  if (species === "goat") return "goat";

  const age = ageDays(a.bornOn, now);
  if (a.stage === "calf" || (age !== null && age < CALF_DAYS)) return "calf";

  if (a.sex === "Male") return a.stage === "bull" ? "bull" : "steer";
  if (a.sex !== "Female") return "steer"; // sex not recorded: the feedlot's usual animal

  if (a.stage === "heifer") return "heifer";
  if (a.stage && CALVED.includes(a.stage)) return "cow";
  // "open" is also what the list sends for every animal still on the farm (the
  // stage proper needs the profile), so age decides between heifer and cow.
  return age !== null && age < HEIFER_DAYS ? "heifer" : "cow";
}

/** FNV-1a over the number: small, fast, and the same in every browser. */
export function tagHash(id: string): number {
  let h = 0x811c9dc5;
  const s = (id || "").trim().toUpperCase();
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export function pickSilhouette(a: SilhouetteSubject, now = new Date()): Silhouette {
  const poses = POSES[silhouetteClass(a, now)];
  return poses[tagHash(a.id) % poses.length];
}
