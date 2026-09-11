# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where everyone stands once a calving is recorded — asked before it is."""

import frappe

from upande_livestock.serverscripts.common import herd_movement
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def calving_destinations(dam=None):
	"""The dam's next herd, and the herd each kind of calf joins.

	A read, so it changes nothing — the point is to put the consequence in front
	of the person at the pen while they can still say it is wrong.
	"""

	def go():
		guard_read("Animal")
		if not dam:
			frappe.throw(frappe._("Select the dam."))
		out = herd_movement.calving_destinations(dam)
		out["ok"] = True
		return out

	return run(go, "livestock calving_destinations failed")
