# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Does this animal have a file open, and what is in her history."""

import frappe

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common.health_case import (
	TREATING_STATUSES,
	days_open,
	open_case_for,
)


@frappe.whitelist()
def case_for_animal(payload=None):
	"""Her open file if she has one, and the last few that were closed.

	ASKED BEFORE TREATING, ALWAYS. The question "does she already have a file
	for this?" is the one the person at the crush cannot answer from memory and
	the one that decides whether today's injection joins an existing course or
	starts a new one. Getting it wrong scatters a single bout of mastitis across
	three files, or buries a fresh illness in a file opened last season.

	The closed ones come too, and deliberately: a cow on her fourth file for the
	same quarter in a year is a different conversation from a cow on her first,
	and neither the open file nor the count of it would tell you that.
	"""

	def go():
		guard_read("Livestock Health Case")
		d = as_dict(payload) if payload else {}
		animal = (d.get("animal") or "").strip()
		if not animal:
			frappe.throw(frappe._("Select an animal."))

		standing = open_case_for(animal)
		if standing:
			standing = {
				**standing,
				"days_open": days_open(standing),
				"treatments": frappe.db.count(
					"Livestock Health Treatment",
					{"parent": standing["name"], "parenttype": "Livestock Health Case"},
				),
			}

		history = frappe.get_all(
			"Livestock Health Case",
			filters={
				"animal": animal,
				"docstatus": 1,
				"case_status": ["not in", TREATING_STATUSES],
			},
			fields=["name", "opened_date", "closed_date", "case_status",
			        "presenting_symptoms", "provisional_diagnosis", "duration_days"],
			order_by="opened_date desc",
			limit_page_length=6,
		)

		return {
			"ok": True,
			"animal": animal,
			"open_case": standing,
			"history": history,
			"closed_count": frappe.db.count("Livestock Health Case", {
				"animal": animal, "docstatus": 1,
				"case_status": ["not in", TREATING_STATUSES],
			}),
		}

	return run(go, "livestock case_for_animal failed")
