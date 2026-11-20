# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""feed_day_program: split out of feeding.feed_actuals; that module still re-exports it, so the old dotted path resolves."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def feed_day_program(date=None, herd=None):
	"""Every herd's formula for a day: planned and actual per component.

	Returns `{ok, date, herds: [{herd, herd_name, date, record, bom, head_count,
	status, amended, planned_kg, actual_kg, planned_per_head, actual_per_head,
	variance_kg, components: [{item_code, item_name, uom, planned_kg, actual_kg,
	planned_per_head, actual_per_head, removed}], draft_entries, stock, remarks}],
	skipped, setup}`.
	"""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.feeding.feed_actuals import day_program


	def go():
		guard_read("Herds")
		out = day_program(date, herd)
		out["ok"] = True
		return out

	return run(go, "livestock feed_day_program failed")
