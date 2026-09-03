"""The single answer to which herds may be milked and which animals may be served.

One call, so a client cannot decide it differently — see the commit that
introduced it. Read-guarded on Herds."""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common import herd_movement


@frappe.whitelist()
def eligibility():
	"""Everything a client needs to offer only what an animal is eligible for.

	One call rather than several, because a mobile client on a farm network
	should not need four round trips to work out whether it may show a cow in a
	milking form. All of it is DERIVED from Herd Movement settings — a client
	that filters on its own hand-marked flags drifts the moment a herd is
	renamed or added, which is what the app was doing with custom_is_milking.
	"""

	def go():
		guard_read("Herds")

		ladder = herd_movement.growth_ladder()
		return {
			"ok": True,
			"milking_herds": herd_movement.milking_herds(),
			"service_herds": herd_movement.service_herds(),
			"service_wait_days": herd_movement.service_wait_days(),
			"growth_ladder": ladder,
			# next_herd per rung, so a client can propose a destination without
			# re-deriving the order and getting it subtly wrong.
			"next_herd": {
				r["herd"]: herd_movement.next_growth_herd(r["herd"])
				for r in ladder
			},
			"calf_herds": {
				"female": herd_movement.calf_herd("Female"),
				"male": herd_movement.calf_herd("Male"),
			},
			"diagnosable": [r["animal"] for r in herd_movement.diagnosable_animals()],
		}

	return run(go, "livestock eligibility failed")
