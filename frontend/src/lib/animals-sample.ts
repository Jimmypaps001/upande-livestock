/**
 * PLACEHOLDER DATA. Delete this file when the endpoints land.
 *
 * Every animal here is a real Kaitet register number in a real herd, because a
 * layout proved against "Animal 1 / Herd A" looks fine right up until it meets
 * "12 MONTHS-SERVICE (BULLYING HEIFERS)" and a cow with eight calvings behind
 * her. The numbers are plausible for an Ayrshire herd in Nakuru; none of them
 * came off the farm's records.
 */
import type { AnimalProfile, AnimalSummary } from "@/lib/animals";

function iso(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

export const SAMPLE_HERD: AnimalSummary[] = [
  { id: "A048/19", name: "HASSAN", sex: "Female", herd: "Lactating group 1", breed: "Ayrshire", bornOn: iso(2630), status: "Active", stage: "confirmed", photo: null },
  { id: "A028/19", name: "DAGMAR", sex: "Female", herd: "Lactating group 1", breed: "Ayrshire", bornOn: iso(2700), status: "Active", stage: "open", photo: null },
  { id: "A061/19", name: "BELLA", sex: "Female", herd: "STEAMERS", breed: "Friesian", bornOn: iso(2560), status: "Active", stage: "dry", photo: null },
  { id: "A054/19", name: "IDD", sex: "Female", herd: "LACTATION GROUP 2", breed: "Ayrshire", bornOn: iso(2610), status: "Active", stage: "served", photo: null },
  { id: "A019/20", name: "DORIS SXI", sex: "Female", herd: "Lactating group 1", breed: "Ayrshire", bornOn: iso(2310), status: "Active", stage: "fresh", photo: null },
  { id: "A027/24", name: "FAVORITE", sex: "Female", herd: "INCALF HEIFERS", breed: "Ayrshire", bornOn: iso(760), status: "Active", stage: "confirmed", photo: null },
  { id: "A013/24", name: "BACARY", sex: "Female", herd: "12 MONTHS-SERVICE (BULLYING HEIFERS)", breed: "Friesian", bornOn: iso(560), status: "Active", stage: "heifer", photo: null },
  { id: "A039/26", name: "NIKKI", sex: "Female", herd: "0-2", breed: "Ayrshire", bornOn: iso(18), status: "Active", stage: "heifer", photo: null },
  { id: "B013/26", name: "B013/26", sex: "Male", herd: "BULLS", breed: "Ayrshire", bornOn: iso(110), status: "Active", stage: "heifer", photo: null },
  { id: "A084/19", name: "BBI", sex: "Female", herd: "Lactation Group 3 TEST HERD", breed: "Friesian", bornOn: iso(2440), status: "Active", stage: "open", photo: null },
];

const PROFILES: Record<string, Omit<AnimalProfile, keyof AnimalSummary>> = {
  "A048/19": {
    dam: "A012/16",
    sire: "Semen · NORDIC RED 4471",
    lastCalving: iso(212),
    expectedCalving: iso(-63),
    cycle: {
      stage: "confirmed",
      dayInStage: 147,
      daysInMilk: 212,
      nextUp: "Dry off",
      nextOn: iso(-3),
    },
    kpis: {
      parity: 5, services: 9, conceptions: 5, abortions: 1,
      conceptionRate: 56, calvingInterval: 398, lactationYield: 6140,
      yieldIndex: 118, treatments: 2,
    },
    spells: [
      { herd: "0-2", from: iso(2630), to: iso(2570) },
      { herd: "2-4", from: iso(2570), to: iso(2510) },
      { herd: "4-12 MONTHS (WEANERS)", from: iso(2510), to: iso(2270) },
      { herd: "12 MONTHS-SERVICE (BULLYING HEIFERS)", from: iso(2270), to: iso(1960) },
      { herd: "INCALF HEIFERS", from: iso(1960), to: iso(1760) },
      { herd: "STEAMERS", from: iso(1760), to: iso(1670) },
      { herd: "Lactating group 1", from: iso(1670), to: null },
    ],
    milestones: [
      { kind: "birth", on: iso(2630), label: "Born", detail: "Out of A012/16" },
      { kind: "movement", on: iso(2270), label: "To weaners" },
      { kind: "service", on: iso(1990), label: "First service", detail: "A.I. · NORDIC RED 4471" },
      { kind: "confirmed", on: iso(1955), label: "Confirmed in calf" },
      { kind: "calving", on: iso(1672), label: "First calving", detail: "Heifer calf · A031/21" },
      { kind: "calving", on: iso(1281), label: "Second calving", detail: "Bull calf" },
      { kind: "abortion", on: iso(1010), label: "Abortion", detail: "At 112 days" },
      { kind: "calving", on: iso(872), label: "Third calving", detail: "Heifer calf · A008/24" },
      { kind: "health", on: iso(640), label: "Mastitis", detail: "Left hind · resolved" },
      { kind: "calving", on: iso(520), label: "Fourth calving", detail: "Heifer calf" },
      { kind: "calving", on: iso(212), label: "Fifth calving", detail: "Bull calf · B009/26" },
      { kind: "service", on: iso(147), label: "Served", detail: "A.I. · NORDIC RED 5120" },
      { kind: "confirmed", on: iso(112), label: "Confirmed in calf" },
    ],
  },
};

/** A profile for any animal in the list, whether or not one was written out. */
export function sampleProfile(summary: AnimalSummary): AnimalProfile {
  const extra = PROFILES[summary.id];
  if (extra) return { ...summary, ...extra };

  // Everyone else gets a shape consistent with their stage, so the page can be
  // walked end to end without ten hand-written records.
  const born = summary.bornOn || iso(400);
  const heifer = summary.stage === "heifer";
  return {
    ...summary,
    dam: heifer ? null : "A040/20",
    sire: heifer ? null : "Semen · NORDIC RED 4471",
    lastCalving: heifer ? null : iso(180),
    expectedCalving: summary.stage === "confirmed" || summary.stage === "dry" ? iso(-90) : null,
    cycle: {
      stage: summary.stage,
      dayInStage: heifer ? 0 : 62,
      daysInMilk: heifer ? null : 180,
      nextUp: heifer ? "First service" : summary.stage === "dry" ? "Calving" : "Pregnancy check",
      nextOn: heifer ? null : iso(-24),
    },
    kpis: {
      parity: heifer ? 0 : 2,
      services: heifer ? 0 : 3,
      conceptions: heifer ? 0 : 2,
      abortions: 0,
      conceptionRate: heifer ? null : 67,
      calvingInterval: heifer ? null : 402,
      lactationYield: heifer ? null : 4980,
      yieldIndex: heifer ? null : 96,
      treatments: 1,
    },
    spells: [{ herd: summary.herd, from: born, to: null }],
    milestones: [
      { kind: "birth", on: born, label: "Born" },
      ...(heifer ? [] : [{ kind: "calving" as const, on: iso(180), label: "Calved" }]),
    ],
  };
}
