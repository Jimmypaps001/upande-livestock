"""Move an animal between herds, recording the move as a Livestock Event."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event


@frappe.whitelist()
def create_movement_event(payload):
	def go():
		guard("Livestock Event")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("new_herd"):
			frappe.throw(_("Select the destination herd."))
		doc = new_livestock_event(d, "Movement")
		doc.new_herd = d.get("new_herd")
		doc.insert()
		doc.submit()  # herd_movement_processor updates Animal.current_herd + headcounts
		return {"ok": True, "name": doc.name}

	return run(go, "livestock create_movement_event failed")
