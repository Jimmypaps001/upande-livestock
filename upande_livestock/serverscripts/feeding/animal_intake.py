# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""animal_intake: split out of feeding.feed_actuals; that module still re-exports it, so the old dotted path resolves."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def animal_intake(herd, date=None):
	"""What each animal in a herd took on a day: actual against planned kg.

	Returns `{ok, herd, date, head_count, planned_kg, actual_kg, variance_kg,
	variance_pct, appetite, totals: {planned_kg, actual_kg, below_plan, above_plan,
	on_plan}, animals: [{animal, tag, planned_kg, actual_kg, variance_kg,
	variance_pct, appetite}]}` (the kg figures are per animal; appetite is
	"below" | "above" | "on_plan", with no threshold).
	"""

	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.feeding.feed_actuals import per_animal_intake


	def go():
		guard_read("Herds")
		out = per_animal_intake(herd, date)
		out["ok"] = True
		return out

	return run(go, "livestock animal_intake failed")
