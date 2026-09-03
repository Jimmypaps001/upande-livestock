"""Record a calving and the calves it produced.

Guards Animal as well as Livestock Event: this creates animals."""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common.employee import employee_or_throw
from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


def _calf_row(calf, outcome):
	"""Normalise one incoming calf dict for record_calf_births."""
	tag = (calf.get("name") or "").strip().upper()
	stillborn = outcome != "Live Birth" or not tag or tag == "STILLBORN"
	return {
		"tag": tag,
		"sex": calf.get("sex"),
		"burn_name": tag,
		"birth_weight": calf.get("birth_weight"),
		"is_stillborn": 1 if stillborn else 0,
		"herd": calf.get("herd"),
		# record_calf_births reads all four off the row and stamps them on the
		# Birth event, which passes them to the Animal. Leaving them out here is
		# what made a birth booked through record_birth arrive with no breed, no
		# condition at birth and no photo.
		"breed": calf.get("breed"),
		"health_status": calf.get("health_status"),
		"vet_remarks": calf.get("vet_remarks"),
		"photo": calf.get("photo"),
	}


@frappe.whitelist()
def record_birth(payload):
	"""Record a calving: a Calving Livestock Event + (for live births) one Animal
	record and a Birth event per calf. Ports the "Record Livestock Birth" Server
	Script into a permission-checked whitelist call. No Stock Entry involved."""

	def go():
		guard("Livestock Event")
		guard("Animal")
		d = as_dict(payload)
		dam_name = d.get("dam") or d.get("animal")
		if not dam_name:
			frappe.throw(_("Select the dam."))
		operator = employee_or_throw(d.get("operator"))
		event_date = d.get("event_date") or today()
		outcome = d.get("outcome") or "Live Birth"
		related_pregnancy = d.get("related_pregnancy") or ""
		remarks = d.get("remarks") or ""
		calves = d.get("calves") or []
		if not isinstance(calves, list) or not calves:
			frappe.throw(_("Add at least one calf."))

		dam = frappe.get_doc("Animal", dam_name)

		# The sire comes off the Service, but `related_pregnancy` can name either
		# link in the chain, so follow whichever arrived.
		#
		# It used to only handle a Pregnancy Diagnosis, hopping Diagnosis ->
		# related_service -> Service. `_validate_pregnancy_link` now rejects a
		# Diagnosis on `custom_related_pregnancy` (every reader of that field
		# joins it against a Service), which left no input for which this both
		# succeeded and found a sire: pass a Diagnosis and the insert below
		# throws; pass a Service and `related_service` is blank, because only a
		# Diagnosis carries it. Every Birth event lost its sire, silently.
		sire = ""
		if related_pregnancy:
			try:
				preg = frappe.get_doc("Livestock Event", related_pregnancy)
				if preg.event_type == "Service":
					sire = preg.sire or ""
				elif preg.related_service:
					svc = frappe.get_doc("Livestock Event", preg.related_service)
					sire = svc.sire or ""
			except Exception:
				pass

		calving = frappe.new_doc("Livestock Event")
		calving.animal = dam_name
		calving.event_type = "Calving"
		calving.event_date = event_date
		calving.current_herd = dam.current_herd or ""
		calving.custom_calving_outcome = outcome
		calving.custom_no_of_calves = len(calves)
		calving.sire = sire
		calving.operator = operator
		calving.remarks = remarks
		if len(calves) == 1 and calves[0].get("sex"):
			calving.custom_calf_sex = calves[0].get("sex")
		if related_pregnancy:
			calving.custom_related_pregnancy = related_pregnancy
		calving.insert()
		calving.submit()

		# One calf-creation path: record_calf_births owns the per-calf loop and lets
		# the Livestock Event controller create each Animal. A second copy of this
		# loop here is what would make a form-booked birth create the calf twice.
		#
		# Gated on outcome, matching the before the reorg behaviour exactly: a Still
		# Birth creates only the Calving, with no Birth events at all. Abortion
		# used to reach this same gate as a custom_calving_outcome value; a later change
		# removed it from that Select entirely (pregnancy loss is now its own
		# Abortion event type — see LivestockEvent.close_pregnancy_after_abortion),
		# so calving.insert() above now rejects outcome="Abortion" itself, before
		# this gate is even reached.
		created = []
		if outcome == "Live Birth":
			created = record_calf_births(
				{
					"calving": calving.name,
					"calves": [_calf_row(c, outcome) for c in calves],
				}
			)["created"]

		return {
			"ok": True,
			"name": calving.name,
			"outcome": outcome,
			"num_calves": len(calves),
			"calves": created,
		}

	return run(go, "livestock record_birth failed")
