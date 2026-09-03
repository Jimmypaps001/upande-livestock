"""What the milking screen offers: the herds that can be milked, and who is recording.

Read-guarded on Milk Recording — the doctype the screen exists to create."""

import frappe

from upande_livestock.serverscripts.common.company import default_company
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common import herd_movement


@frappe.whitelist()
def milking_options():
	"""Herds that are actually in milk.

	Offering every herd let a milking be recorded against calves and dry cows.
	The lactation groups are read off Herd Movement settings rather than marked
	by hand, because a hand-marked list drifts the first time a herd is renamed
	or added.
	"""

	def go():
		guard_read("Milk Recording")
		from upande_livestock.serverscripts.common import herd_movement

		allowed = herd_movement.milking_herds()
		filters = {"name": ["in", allowed]} if allowed else None
		herds = frappe.get_all(
			"Herds", filters=filters, fields=["name", "herd_name", "cost_center"],
			order_by="herd_name asc",
		)
		return {
			"ok": True,
			"herds": [{"name": h.name, "label": h.herd_name or h.name} for h in herds],
			"restricted_to": allowed,
			"company": default_company(),
			"employee": current_employee(),
		}

	return run(go, "livestock milking_options failed")
