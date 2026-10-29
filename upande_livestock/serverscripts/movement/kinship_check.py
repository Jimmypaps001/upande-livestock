# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What a move would say about kinship, before anybody confirms it.

The phone calls this when the user picks a destination, so the warning and the
selection-note requirement are in front of him, not after he saved. It answers
the same questions the Movement event asks on save (common/beef_events), so the
preview and the write cannot disagree.
"""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import beef_events, kinship
from upande_livestock.serverscripts.common.beef_settings import kinship_check_on
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def kinship_check(animal, herd):
	"""`{warnings, conflicts, selection, note_required, stream}` for moving `animal` into `herd`."""

	def go():
		guard_read("Animal")
		row = frappe.db.get_value("Animal", animal, ["current_herd", "sex"], as_dict=True)
		if not row:
			frappe.throw(_("{0} is not an animal on this farm.").format(animal))
		if not frappe.db.exists("Herds", herd):
			frappe.throw(_("{0} is not a herd on this farm.").format(herd))
		selection = beef_events.is_selection(animal, row.current_herd, herd)
		cls = beef_events.herd_class(herd)
		conflicts = kinship.conflicts(animal, herd) if kinship_check_on() and cls == "Breeding" else []
		stream = None
		if row.sex == "Male":
			stream = "Feedlot" if cls == "Fattening" else "Breeding" if selection else None
		return {
			"ok": True,
			"animal": animal,
			"herd": herd,
			"warnings": beef_events.warnings_for_move(animal, herd),
			"conflicts": conflicts,
			"selection": selection,
			"note_required": selection,
			"stream": stream,
		}

	return run(go, "livestock kinship_check failed")
