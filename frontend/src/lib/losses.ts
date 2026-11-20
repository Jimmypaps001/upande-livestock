/** The loss flow's calls: record a loss, follow its trail, the claims list and the scenarios. */
import { call } from "@/lib/frappe";
import { bootstrap } from "@/lib/frappe";

const API = "upande_livestock.serverscripts.losses";

export const TRIGGERS = ["Injury", "Disease", "Death", "Theft", "Low production", "Other"] as const;
export const OUTCOMES = ["Sell for slaughter", "Sell live", "Write off"] as const;
export const SALE_OUTCOMES: readonly string[] = ["Sell for slaughter", "Sell live"];
export const TREATMENTS = ["Repair", "Total Loss", "Impairment"] as const;

export interface LossDocument {
  document_name: string;
  mandatory: number;
}

export interface LossScenario {
  name: string;
  scenario_name: string;
  active: number;
  trigger: string;
  outcome: string;
  description: string | null;
  claim_insurance: number;
  incident_type: string | null;
  loss_treatment: string | null;
  notify_roles: string | null;
  required_documents: LossDocument[];
}

export interface ClaimInfo {
  name: string;
  status: string;
  amount_claimed: number | null;
  amount_approved: number | null;
  amount_received: number | null;
  outstanding_amount: number | null;
  missing_documents: string[];
}

export interface DisposalInfo {
  name: string;
  docstatus: number;
  disposal_type: string;
  disposal_date: string;
  sale_price: number | null;
  customer: string | null;
  sales_invoice: string | null;
  invoice_status?: number | null;
}

export interface LossTrail {
  name: string;
  animal: string;
  scenario: string;
  trigger: string | null;
  outcome: string | null;
  incident_date: string;
  notes: string | null;
  status: string;
  claim: ClaimInfo | null;
  claim_note: string | null;
  disposal: DisposalInfo | null;
  waiting_for: string | null;
  requirement: string;
}

export interface ClaimRow {
  name: string;
  animal: string;
  animal_name: string | null;
  scenario: string;
  incident_date: string;
  claim: string;
  claim_status: string | null;
  status: string;
  disposal: string | null;
  sales_invoice: string | null;
  missing_documents: string | null;
  amount_claimed?: number | null;
  amount_approved?: number | null;
  amount_received?: number | null;
  outstanding_amount?: number | null;
}

export interface RecordedLoss {
  name: string;
  status: string;
  claim: string | null;
  claim_status: string | null;
  claim_note: string | null;
  missing_documents: string | null;
  disposal: string | null;
  disposal_note: string | null;
  blocked: string | null;
}

export function getLossScenarios(includeInactive = false) {
  return call<{ scenarios: LossScenario[]; requirement: string; incident_types: string[] }>(
    `${API}.loss_scenarios.loss_scenarios`,
    { payload: { include_inactive: includeInactive ? 1 : 0 } },
  );
}

export function saveLossScenario(s: Partial<LossScenario>) {
  return call<{ scenario: LossScenario }>(`${API}.save_loss_scenario.save_loss_scenario`, { payload: s });
}

export function deleteLossScenario(name: string) {
  return call<{ deleted: boolean; message?: string }>(`${API}.delete_loss_scenario.delete_loss_scenario`, { payload: { name } });
}

export function recordLoss(p: {
  animal: string;
  scenario: string;
  incident_date: string;
  notes?: string;
  documents?: { document_name: string; attachment?: string; remarks?: string }[];
  customer?: string;
  sale_price?: number;
  buyer_name?: string;
}) {
  return call<RecordedLoss>(`${API}.record_loss.record_loss`, { payload: p });
}

export function completeLoss(p: { loss_name: string; customer?: string; sale_price?: number; buyer_name?: string }) {
  return call<{ name: string; status: string }>(`${API}.complete_loss.complete_loss`, { payload: p });
}

export function getLossTrail(animal: string) {
  return call<{ losses: LossTrail[]; requirement: string; cover: string }>(`${API}.loss_trail.loss_trail`, {
    payload: { animal },
  });
}

export function getLossClaims(status?: string) {
  return call<{ claims: ClaimRow[]; requirement: string }>(`${API}.loss_claims.loss_claims`, {
    payload: status ? { status } : {},
  });
}

/** Managers edit scenarios; the server refuses everyone else too. */
export const SCENARIO_ROLES = ["Livestock Manager", "System Manager"];

export function canEditScenarios(roles: string[] = bootstrap().roles): boolean {
  return roles.some((r) => SCENARIO_ROLES.includes(r) || r === "Administrator");
}

/** The step of the trail each status of a loss has reached, for the card. */
export function trailSteps(t: LossTrail): { label: string; detail: string; done: boolean }[] {
  const steps = [{ label: "Incident", detail: `${t.scenario}, ${t.incident_date}`, done: true }];
  if (t.claim) {
    steps.push({ label: "Claim", detail: `${t.claim.name} · ${t.claim.status}`, done: t.claim.status !== "Draft" });
  } else if (t.claim_note) {
    steps.push({ label: "Claim", detail: t.claim_note, done: false });
  }
  steps.push({
    label: "Disposal",
    detail: t.disposal ? `${t.disposal.name} · ${t.disposal.docstatus === 1 ? "posted" : "draft"}` : "not yet",
    done: t.disposal?.docstatus === 1,
  });
  if (t.outcome !== "Write off") {
    const inv = t.disposal?.sales_invoice;
    steps.push({
      label: "Invoice",
      detail: inv ? `${inv} · ${t.disposal?.invoice_status === 1 ? "submitted" : "draft"}` : "not yet",
      done: t.disposal?.invoice_status === 1,
    });
  }
  if (t.claim) {
    const c = t.claim;
    steps.push({
      label: "Settlement",
      detail: c.amount_received ? `received ${c.amount_received} of ${c.amount_approved ?? 0}` : "not yet",
      done: ["Settled", "Closed"].includes(c.status),
    });
  }
  return steps;
}
