"""Record the result of a pregnancy check.

Consumes nothing, so it posts no Stock Entry."""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event
from upande_livestock.serverscripts.husbandry._shared import append_items
from upande_livestock.serverscripts.common import herd_movement, natural_service


@frappe.whitelist()
def create_pregnancy_diagnosis(payload):
	"""Record a Pregnancy Diagnosis (Livestock Event only). The Server Script
	auto-links the related service when omitted and validates timing."""

	def go():

		guard("Livestock Event")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("diagnosis_result"):
			frappe.throw(_("Select a diagnosis result."))
		# A diagnosis answers a question a service asked. Without an open service
		# there is nothing to diagnose, and a "Confirmed" would invent a pregnancy
		# out of nothing — which then drives calving and herd moves.
		#
		# One way in: natural service is recorded when it is perceived, so a vet's
		# perceived conception date (or the foetal age in weeks) makes the Natural
		# Service this diagnosis answers.
		created = None
		if not d.get("related_service") and not herd_movement.has_open_service(d["animal"]):
			conception = natural_service.conception_from(d, d.get("diagnosis_date") or today())
			if not conception:
				frappe.throw(
					_("{0} has no service awaiting a pregnancy check. Record the service first, "
					  "or give the perceived conception date.").format(d["animal"])
				)
			created = natural_service.create_natural_service(
				d["animal"], conception, operator=d.get("operator"),
				sire_animal=d.get("sire_animal") or None, sire_unknown=bool(d.get("sire_unknown")),
				remarks=_("Derived from the pregnancy diagnosis"))
			d["related_service"] = created.name
		doc = new_livestock_event(d, "Pregnancy Diagnosis", date_key="diagnosis_date")
		doc.diagnosis_date = d.get("diagnosis_date") or today()
		doc.diagnosis_result = d.get("diagnosis_result")
		doc.diagnosis_remarks = d.get("diagnosis_remarks")
		if d.get("related_service"):
			doc.related_service = d.get("related_service")
		append_items(doc, d)
		doc.insert()
		doc.submit()
		out = {"ok": True, "name": doc.name, "result": doc.diagnosis_result,
		       "service": doc.related_service, "service_created": bool(created),
		       "created": {"pregnancy_diagnosis": doc.name, "service": created.name if created else None},
		       "warnings": []}
		out.update(natural_service.sire_report(created or doc.related_service))
		return out

	return run(go, "livestock create_pregnancy_diagnosis failed")
