# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Move several weight-band boundaries in one go."""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import as_dict, guard_write, run
from upande_livestock.upande_livestock.doctype.herds.herds import check_ladder


@frappe.whitelist()
def save_band_ladder(bands):
	"""Apply every band change in one transaction, then judge the ladder once.

	Two neighbouring bands share a boundary (150-250 / 250-350), so moving it
	means editing both herds. Saved one at a time, the first save is always an
	overlap or a gap. Here each herd is written with its own ladder check
	suspended, then the resulting Fattening ladder is validated as a whole; a
	refusal rolls everything back and comes back as {"error": msg}.

	`bands` is a list of {"herd", "min_weight_kg", "max_weight_kg",
	"target_adg_kg"?}; 0 for the max leaves the top band open-ended.
	"""

	def go():
		guard_write("Herds")
		rows = bands if isinstance(bands, list) else as_dict(bands)
		if isinstance(rows, dict):
			rows = rows.get("bands") or []
		if not rows:
			frappe.throw(_("There are no bands to save."))
		frappe.db.savepoint("band_ladder")
		try:
			return _apply(rows)
		except frappe.ValidationError as e:
			# A refused ladder is an answer, not a fault: undo just this call's
			# writes and say why.
			frappe.db.rollback(save_point="band_ladder")
			return {"error": str(e)}

	return run(go, "livestock save_band_ladder failed")


def _apply(rows):
	for row in rows:
		herd = row.get("herd")
		if not frappe.db.exists("Herds", herd):
			frappe.throw(_("There is no herd called {0}.").format(herd))
		if frappe.db.get_value("Herds", herd, "herd_class") != "Fattening":
			frappe.throw(_("{0} is not a Fattening herd.").format(herd))
		doc = frappe.get_doc("Herds", herd)
		doc.flags.ignore_permissions = True
		doc.flags.ladder_check_suspended = True
		doc.min_weight_kg = flt(row.get("min_weight_kg"))
		doc.max_weight_kg = flt(row.get("max_weight_kg"))
		if row.get("target_adg_kg") not in (None, ""):
			doc.target_adg_kg = flt(row.get("target_adg_kg"))
		doc.save()

	ladder = frappe.get_all(
		"Herds", filters={"herd_class": "Fattening"},
		fields=["name", "min_weight_kg", "max_weight_kg", "target_adg_kg"],
	)
	check_ladder([
		{"herd": r.name, "min": flt(r.min_weight_kg), "max": flt(r.max_weight_kg) or None}
		for r in ladder
	])
	ladder.sort(key=lambda r: flt(r.min_weight_kg))
	return {"ok": True, "bands": [
		{"herd": r.name, "min_weight_kg": flt(r.min_weight_kg),
		 "max_weight_kg": flt(r.max_weight_kg), "target_adg_kg": flt(r.target_adg_kg)}
		for r in ladder
	]}
