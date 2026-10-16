"""Which animals a husbandry round would record, and which it would skip."""

import frappe

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.husbandry._shared import (
	HUSBANDRY_TYPES,
	_husbandry_targets,
	split_eligible,
)


@frappe.whitelist()
def round_eligibility(payload):
	"""Preview a round: {eligible: [animal], skipped: [{animal, reason}]}.

	Takes what create_husbandry_event takes (event_type, animals / herd, and the
	date). Read-only, and only advice: create_husbandry_event decides again on
	save, so an animal that became eligible or ineligible in between is
	handled by the server, not by this answer.
	"""

	def go():
		guard_read("Livestock Event")
		d = as_dict(payload)
		event_type = d.get("event_type")
		if event_type not in HUSBANDRY_TYPES:
			frappe.throw(frappe._("{0} is not a husbandry event type.").format(event_type or ""))
		animals = _husbandry_targets(d)
		date, backdated = backdate.resolve(d)
		eligible, skipped = split_eligible(animals, event_type, date, backdated)
		return {"ok": True, "event_type": event_type, "eligible": eligible, "skipped": skipped}

	return run(go, "livestock round_eligibility failed")
