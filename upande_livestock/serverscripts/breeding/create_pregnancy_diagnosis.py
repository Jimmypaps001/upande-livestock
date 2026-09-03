"""Record the result of a pregnancy check.

Consumes nothing, so it posts no Stock Entry."""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event
from upande_livestock.serverscripts.common import herd_movement


@frappe.whitelist()
def create_pregnancy_diagnosis(payload):
	"""Record a Pregnancy Diagnosis (Livestock Event only). The Server Script
	auto-links the related service when omitted and validates timing."""

	def go():
		from upande_livestock.serverscripts.common import herd_movement

		guard("Livestock Event")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("diagnosis_result"):
			frappe.throw(_("Select a diagnosis result."))
		# A diagnosis answers a question a service asked. Without an open service
		# there is nothing to diagnose, and a "Confirmed" would invent a pregnancy
		# out of nothing — which then drives calving, herd moves and milk.
		if not d.get("related_service") and not herd_movement.has_open_service(d["animal"]):
			frappe.throw(
				_("{0} has no service awaiting a pregnancy check. Record the service first.").format(
					d["animal"]
				)
			)
		doc = new_livestock_event(d, "Pregnancy Diagnosis", date_key="diagnosis_date")
		doc.diagnosis_date = d.get("diagnosis_date") or today()
		doc.diagnosis_result = d.get("diagnosis_result")
		doc.diagnosis_remarks = d.get("diagnosis_remarks")
		if d.get("related_service"):
			doc.related_service = d.get("related_service")
		doc.insert()
		doc.submit()
		return {"ok": True, "name": doc.name, "result": doc.diagnosis_result}

	return run(go, "livestock create_pregnancy_diagnosis failed")
