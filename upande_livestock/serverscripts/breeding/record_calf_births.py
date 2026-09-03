"""Record the individual calves against an existing Calving.

The one place that creates a calf Animal — the Livestock Event controller does
the creation, this owns the per-calf loop."""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.upande_livestock.doctype.livestock_event.livestock_event import (
	warn_on_calving_mismatch,
)


@frappe.whitelist()
def record_calf_births(payload):
	"""Create one Birth event per calf for an existing Calving event.

	A dam bearing triplets gets one Calving event and three Birth events. Stillborn
	rows are recorded as Birth events that create no Animal, so the calving's count
	stays honest without inflating herd numbers — a dam with twins where one lives
	and one dies is two rows with two different outcomes, not an average.

	Each live calf carries its own breed, condition at birth and photo, and is
	routed to a herd by its sex.
	"""

	def go():
		guard("Livestock Event")
		guard("Animal")
		d = as_dict(payload)
		calving_name = d.get("calving")
		if not calving_name:
			frappe.throw(_("Select the calving event."))
		calves = d.get("calves") or []
		if not isinstance(calves, list) or not calves:
			frappe.throw(_("Add at least one calf."))

		calving = frappe.get_doc("Livestock Event", calving_name)
		if calving.event_type != "Calving":
			frappe.throw(_("{0} is not a Calving event.").format(calving_name))

		dam_name = calving.animal
		dam = frappe.get_doc("Animal", dam_name)
		created = []

		# Suppress the per-Birth mismatch warning for the duration of this loop:
		# each Birth's own on_submit recounts against the calving's FULL expected
		# total, so without this a 3-calf batch would warn "expects 3, got 1"
		# after the first calf and "expects 3, got 2" after the second — false
		# alarms on a batch that is about to complete correctly. births_recorded
		# itself is still refreshed on every single Birth submit regardless (see
		# LivestockEvent.refresh_calving_birth_count); only the message is held
		# back here, evaluated once, after the whole batch, against the final
		# count. The finally ensures an exception mid-loop can't leave the flag
		# set for the rest of the request.
		frappe.flags.suppress_calving_mismatch_warning = True
		try:
			for calf in calves:
				stillborn = bool(calf.get("is_stillborn"))
				birth = frappe.new_doc("Livestock Event")
				birth.event_type = "Birth"
				birth.event_date = calving.event_date
				birth.operator = calving.operator
				birth.dam = dam_name
				birth.related_calving = calving.name
				birth.sire = calving.sire
				birth.is_stillborn = 1 if stillborn else 0

				if stillborn:
					birth.remarks = f"Stillborn. Dam: {dam.tag_number or dam.burn_name}"
				else:
					birth.calf_tag_number = (calf.get("tag") or "").strip().upper()
					birth.calf_sex = calf.get("sex") if calf.get("sex") in ("Female", "Male") else "Female"
					birth.calf_burn_name = calf.get("burn_name") or birth.calf_tag_number
					birth.calf_birth_weight_kg = flt(calf.get("birth_weight"))
					# An empty/omitted herd must still fall back to resolve_calf_herd() —
					# create_calf_if_needed() treats a falsy herd the same as "not given",
					# and that fallback now routes on sex.
					birth.calf_herd = calf.get("herd") or ""
					birth.calf_breed = calf.get("breed") or None
					birth.calf_health_status = calf.get("health_status") or None
					birth.calf_vet_remarks = calf.get("vet_remarks") or None
					birth.calf_photo = calf.get("photo") or None
					birth.remarks = f"Dam: {dam.tag_number or dam.burn_name}"

				birth.insert()
				birth.submit()
				if not stillborn:
					created.append({
						"animal": birth.animal,
						"tag": birth.calf_tag_number,
						"sex": birth.calf_sex,
						"herd": frappe.db.get_value("Animal", birth.animal, "current_herd"),
						"breed": frappe.db.get_value("Animal", birth.animal, "breed"),
						"health_status": birth.calf_health_status,
					})
		finally:
			frappe.flags.suppress_calving_mismatch_warning = False

		# One evaluation for the whole batch, against the final, settled count —
		# not one per calf (see the comment above the loop).
		warn_on_calving_mismatch(calving.name)

		calving.reload()
		return {"ok": True, "created": created, "births_recorded": calving.births_recorded}

	return run(go, "livestock record_calf_births failed")
