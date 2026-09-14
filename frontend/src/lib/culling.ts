/**
 * The four ways an animal leaves the farm.
 *
 * The flow names, the gate names and the order between them are the server's
 * — serverscripts/common/culling.py owns them, and duplicating that ordering
 * here would let the page offer a button the server then refuses. What this
 * file adds is the reading of a case, not a second opinion about it.
 */
import { call, type Envelope } from "@/lib/frappe";
import type { AnimalSummary } from "@/lib/animals";

const NS = "upande_livestock.serverscripts.culling";
const BOARD = `${NS}.cull_board.cull_board`;
const EVIDENCE = `${NS}.cull_evidence.cull_evidence`;
const RAISE = `${NS}.raise_cull.raise_cull`;
const VERDICT = `${NS}.vet_verdict.vet_verdict`;
const APPROVE = `${NS}.approve_cull.approve_cull`;
const REJECT = `${NS}.reject_cull.reject_cull`;
const POST = `${NS}.post_cull.post_cull`;
const MORTALITY = `${NS}.record_mortality.record_mortality`;
const SETTLE = `${NS}.settle_insurance_claim.settle_insurance_claim`;
const CANDIDATES = `${NS}.cull_candidates.cull_candidates`;

export type Flow = "Sale" | "Disposal" | "Mortality" | "Gift";
export type ReviewStatus =
  | "Draft"
  | "Awaiting Vet"
  | "Awaiting Approval"
  | "Approved"
  | "Rejected"
  | "Posted";

export const FLOWS: { flow: Flow; label: string; blurb: string }[] = [
  {
    flow: "Sale",
    label: "Sell her",
    blurb: "A vet passes her fit, then a manager agrees the buyer and the price.",
  },
  {
    flow: "Disposal",
    label: "Dispose of her",
    blurb: "For a sick animal. The vet's recommendation is the decision.",
  },
  {
    flow: "Mortality",
    label: "Record a death",
    blurb: "Already happened. Nobody approves it — it is recorded and posted at once.",
  },
  {
    flow: "Gift",
    label: "Give her away",
    blurb: "No health question. A manager signs, and the recipient is recorded.",
  },
];

/**
 * The causes a death may be recorded under.
 *
 * A fixed list, and the same one the server holds: "sick" typed forty ways is
 * the reason no farm can say what it loses cows to. Detail goes in the remarks.
 */
export const DEATH_CAUSES = [
  "Disease — mastitis",
  "Disease — East Coast Fever",
  "Disease — other tick-borne",
  "Disease — other",
  "Calving complications",
  "Metabolic (milk fever, ketosis, bloat)",
  "Injury / accident",
  "Predation",
  "Poisoning",
  "Old age",
  "Unknown",
] as const;

export const VERDICTS = ["Fit for sale", "Not fit for sale", "Recommends disposal"] as const;
export type Verdict = (typeof VERDICTS)[number];

export interface CullCase {
  name: string;
  animal: string;
  animal_name: string | null;
  herd: string | null;
  disposal_date: string;
  disposal_type: string;
  flow: Flow;
  status: ReviewStatus;
  waiting_on: string;
  evidence: string | null;
  was_productive: boolean;
  death_cause: string | null;
  vet_verdict: Verdict | null;
  vet_on: string | null;
  sale_price: number;
  buyer_name: string | null;
  gifted_to: string | null;
}

export interface FlaggedAnimal {
  name: string;
  burn_name: string | null;
  herd: string | null;
  reason: string | null;
  marked_on: string | null;
  marked_by: string | null;
}

export interface DepartedAnimal {
  name: string;
  animal: string;
  animal_name: string | null;
  disposal_date: string;
  disposal_type: string;
  flow: Flow | null;
  death_cause: string | null;
  sale_price: number;
  sales_invoice: string | null;
  journal_entry: string | null;
  claim: string | null;
  claim_status: string | null;
  claimed_amount: number | null;
  payout_amount: number | null;
}

export interface OpenClaim {
  name: string;
  animal: string;
  policy: string;
  claim_date: string;
  cause: string | null;
  claimed_amount: number;
  status: string;
}

export interface FarmAnimal {
  name: string;
  burn_name: string | null;
  sex: "Female" | "Male";
  current_herd: string | null;
  breed: string | null;
  date_of_birth: string | null;
  image: string | null;
}

export interface CullBoard {
  animals: FarmAnimal[];
  cases: CullCase[];
  flagged: FlaggedAnimal[];
  recent: DepartedAnimal[];
  open_claims: OpenClaim[];
  counts: {
    awaiting_vet: number;
    awaiting_approval: number;
    ready_to_post: number;
    flagged: number;
  };
}

export interface Policy {
  name: string;
  insurer: string | null;
  payout_percent: number | null;
  insured_value: number | null;
  end_date: string | null;
}

export interface Evidence {
  animal: string;
  name: string;
  herd: string | null;
  status: string;
  measures: { key: string; label: string; hers: number | null; herd: number | null; below: boolean; hint: string }[];
  below: number;
  measured: number;
  was_productive: boolean;
  case: string;
  book_value: number;
  is_capitalised: boolean;
  asset: string | null;
  policy: Policy | null;
}

export function getCullBoard(): Promise<Envelope<CullBoard>> {
  return call<CullBoard>(BOARD, { payload: {} });
}

export function getCullEvidence(animal: string): Promise<Envelope<Evidence>> {
  return call<Evidence>(EVIDENCE, { animal });
}

export interface RaiseInput {
  animal: string;
  flow: Flow;
  reason?: string;
  disposal_date?: string;
  death_cause?: string;
  gifted_to?: string;
  buyer_name?: string;
  sale_price?: number;
}

export function raiseCull(input: RaiseInput) {
  return call<{ name: string; status: ReviewStatus; evidence: string; was_productive: boolean; policy: Policy | null }>(
    RAISE,
    { payload: input },
  );
}

export function vetVerdict(caseName: string, verdict: Verdict, notes?: string) {
  return call<{ name: string; status: ReviewStatus; verdict: Verdict }>(VERDICT, {
    payload: { case: caseName, verdict, notes },
  });
}

export function approveCull(caseName: string, terms: { sale_price?: number; buyer_name?: string; customer?: string } = {}) {
  return call<{ name: string; status: ReviewStatus }>(APPROVE, {
    payload: { case: caseName, ...terms },
  });
}

export function rejectCull(caseName: string, reason: string) {
  return call<{ name: string; status: ReviewStatus }>(REJECT, {
    payload: { case: caseName, reason },
  });
}

export function postCull(caseName: string, operator?: string) {
  return call<{
    name: string;
    animal: string;
    animal_status: string;
    herd_before: string | null;
    herd_now: string | null;
    claim: { name: string; insurer: string; claimed_amount: number } | null;
  }>(POST, { payload: { case: caseName, operator } });
}

export function recordMortality(input: {
  animal: string;
  death_cause: string;
  remarks?: string;
  death_date?: string;
  operator?: string;
}) {
  return call<{ name: string; animal: string; claim: { name: string; claimed_amount: number } | null }>(
    MORTALITY,
    { payload: input },
  );
}

export function settleClaim(claim: string, status: "Submitted" | "Paid" | "Rejected", payout_amount?: number, remarks?: string) {
  return call<{ name: string; status: string; payout_amount: number; shortfall: number }>(SETTLE, {
    payload: { claim, status, payout_amount, remarks },
  });
}

/**
 * The one word for what a case is waiting on, for a badge.
 *
 * Derived from the status rather than stored, because the server is the only
 * thing that moves a case and the page must never look ahead of it.
 */
export function toneFor(status: ReviewStatus): "wait" | "ready" | "done" | "stopped" {
  if (status === "Approved") return "ready";
  if (status === "Posted") return "done";
  if (status === "Rejected") return "stopped";
  return "wait";
}

/**
 * The farm's roster in the shape the animal search speaks.
 *
 * The cycle stage is not carried: working it out needs the breeding history,
 * and on this page it would only tint a dot. Everything here is still on the
 * farm by construction — the board serves only active animals — so they all
 * read as `open` rather than claiming a stage nobody computed.
 */
export function asSummaries(animals: FarmAnimal[]): AnimalSummary[] {
  return animals.map((a) => ({
    id: a.name,
    name: a.burn_name || a.name,
    sex: a.sex,
    herd: a.current_herd || "no herd",
    breed: a.breed,
    bornOn: a.date_of_birth,
    status: "Active",
    stage: "open",
    photo: a.image,
  }));
}

/** Why one cow is on the suggested list, and what it is worth in the ranking. */
export interface CullReason {
  key: "abortions" | "not_holding" | "open" | "sick" | "interval" | "produce";
  label: string;
  detail: string;
  weight: number;
}

/** Her figure beside the herd's. Higher is worse on every measure here. */
export interface CullBar {
  label: string;
  hers: number;
  herd: number;
  unit: string;
  worse: boolean;
}

export interface CullYear {
  year: number;
  calvings: number;
  abortions: number;
  services: number;
  sick_days: number;
}

export interface CullCandidate {
  animal: string;
  name: string;
  herd: string | null;
  status: string;
  age_days: number | null;
  score: number;
  reasons: CullReason[];
  bars: CullBar[];
  years: CullYear[];
}

export interface CullCandidates {
  candidates: CullCandidate[];
  considered: number;
  flagged_count: number;
  herd: {
    calving_interval: number | null;
    open_days: number | null;
    sick_days: number | null;
  };
  /** False on this farm — Milk Recording is per herd, so "low produce" cannot
   *  mean litres and the screen says so rather than implying otherwise. */
  per_animal_milk: boolean;
}

export const getCullCandidates = (limit?: number) =>
  call<CullCandidates>(CANDIDATES, { payload: { limit } });
