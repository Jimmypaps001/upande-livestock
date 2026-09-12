# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A death, recorded and posted in one act."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.common.envelope import as_dict, run
from upande_livestock.serverscripts.culling.post_cull import post_cull
from upande_livestock.serverscripts.culling.raise_cull import raise_cull

CAUSES = (
	"Disease — mastitis",
	"Disease — East Coast Fever",
	"Disease — other tick-borne",
	"Disease — other",
	"Calving complications",
	"Metabolic (milk fever, ketosis, bloat)",
	"Injury / accident",
	"Predation",
	"Poisoning",
	"Old age",
	"Unknown",
)


@frappe.whitelist()
def record_mortality(payload):
	"""Record a death: raise the case and post it in the same call.

	NOBODY APPROVES A DEATH. The other three flows ask permission because the
	farm is choosing to lose the animal; a death has already happened, and a
	dead cow sitting in Lactating 1 waiting for a signature is how feed gets
	mixed for her the next morning. Who may record one is still a permission
	question — see culling.assert_may_post — and on the shipped permissions
	that is management, the same as every other departure.

	The cause comes from a fixed list rather than free text. "Sick" typed forty
	different ways is the reason no farm can tell you what it loses cows to, and
	this list is the difference between a mortality figure and a mortality
	pattern. `remarks` is where the detail goes.
	"""

	def go():
		d = as_dict(payload)
		cause = (d.get("death_cause") or "").strip()
		if cause not in CAUSES:
			frappe.throw(
				_("Choose a cause of death from the list. Free text cannot be counted, "
				  "and the pattern across a year is the point of recording it. "
				  "Detail goes in the remarks.")
			)

		raised = raise_cull({
			"animal": d.get("animal"),
			"flow": culling.MORTALITY,
			"death_cause": cause,
			"disposal_date": d.get("death_date") or d.get("disposal_date"),
			"reason": d.get("remarks"),
		})
		if not raised.get("ok"):
			return raised

		posted = post_cull({"case": raised["name"], "operator": d.get("operator")})
		if not posted.get("ok"):
			return posted

		return {**posted, "death_cause": cause, "was_productive": raised["was_productive"]}

	return run(go, "livestock record_mortality failed")
