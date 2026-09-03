"""Record a routine check-up as a Livestock Diagnosis."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common.company import company_or_throw
from upande_livestock.serverscripts.common.employee import employee_or_throw
from upande_livestock.serverscripts.husbandry._shared import _clean_drug_rows
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common import stock as livestock_stock


@frappe.whitelist()
def create_check_up(payload):
	"""Record a routine check-up as a Livestock Diagnosis.

	LivestockDiagnosis.on_submit() calls sync_event_for(self, "Check Up"), so the
	animal's timeline event is created by the doctype — not here.
	"""

	def go():
		guard("Livestock Diagnosis")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("action_taken"):
			frappe.throw(_("Select the action taken."))
		doc = frappe.new_doc("Livestock Diagnosis")
		doc.animal = d.get("animal")
		doc.company = company_or_throw(d.get("company"))
		doc.diagnosis_date = d.get("diagnosis_date") or today()
		doc.operator = employee_or_throw(d.get("operator"))
		doc.reason_for_check = d.get("reason_for_check")
		doc.appearance = d.get("appearance") or None
		doc.hydration = d.get("hydration") or None
		doc.temperature_c = flt(d.get("temperature_c")) or None
		doc.respiration_rate = int(flt(d.get("respiration_rate"))) or None
		doc.heart_rate = int(flt(d.get("heart_rate"))) or None
		doc.bcs = flt(d.get("bcs")) or None
		doc.lameness_score = int(flt(d.get("lameness_score"))) or None
		doc.suggested_disease = d.get("suggested_disease") or None
		doc.differential_notes = d.get("differential_notes")
		doc.action_taken = d.get("action_taken")
		doc.action_notes = d.get("action_notes")
		doc.follow_up_date = d.get("follow_up_date") or None
		# Anything given at the check. LivestockDiagnosis.post_drug_issue posts these
		# out of the drug store on submit, and blocks the check if it cannot.
		for drug in _clean_drug_rows(d.get("drugs"), d.get("source_warehouse") or livestock_stock.drug_warehouse()):
			doc.append("drug_issues", drug)
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"action_taken": doc.action_taken,
			"stock_entry": doc.stock_entry or "",
			"drugs_issued": len(doc.drug_issues or []),
		}

	return run(go, "livestock create_check_up failed")
