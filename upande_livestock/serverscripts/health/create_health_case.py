"""Open a health case for an animal."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common.company import company_or_throw
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


@frappe.whitelist()
def create_health_case(payload):
	"""Open a Livestock Health Case.

	LivestockHealthCase.on_submit() calls sync_event_for(self, "Health Case"), so
	the timeline event is the doctype's job. Treatments are added on the case
	itself afterwards — this endpoint opens the case, it does not close it.
	"""

	def go():
		guard("Livestock Health Case")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("presenting_symptoms"):
			frappe.throw(_("Describe the presenting symptoms."))
		doc = frappe.new_doc("Livestock Health Case")
		doc.animal = d.get("animal")
		doc.company = company_or_throw(d.get("company"))
		doc.opened_date = d.get("opened_date") or today()
		doc.opened_by = d.get("opened_by") or current_employee()
		doc.case_status = d.get("case_status") or "Open"
		doc.presenting_symptoms = d.get("presenting_symptoms")
		doc.body_systems = d.get("body_systems")
		doc.provisional_diagnosis = d.get("provisional_diagnosis") or None
		doc.severity = d.get("severity") or None
		doc.vet_called = 1 if d.get("vet_called") else 0
		doc.vet_name = d.get("vet_name")
		# Treatments given at the point of opening. Each row naming a drug_item is
		# issued out of the drug store by LivestockHealthCase.on_submit; further
		# treatments are added on the case itself later.
		for t in d.get("treatments") or []:
			if not (t.get("drug_item") or t.get("drug_name_text")):
				continue
			doc.append(
				"treatments",
				{
					"treatment_date": t.get("treatment_date") or today(),
					"drug_item": t.get("drug_item") or None,
					"drug_name_text": t.get("drug_name_text"),
					"dosage": t.get("dosage"),
					"qty": flt(t.get("qty")) or 1,
					"route": t.get("route") or None,
					"withdrawal_period_days": int(flt(t.get("withdrawal_period_days"))) or None,
					"administered_by": t.get("administered_by") or current_employee(),
					"notes": t.get("notes"),
				},
			)
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"case_status": doc.case_status,
			"treatments": len(doc.treatments or []),
			"drug_stock_entry": doc.drug_stock_entry or "",
		}

	return run(go, "livestock create_health_case failed")
