# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Every animal the Animals page can search, with enough to draw a row.

Deliberately NOT the profile. The search list is drawn thirty times a second as
somebody types and the profile walks an animal's whole event history; asking for
both together would make the page as slow as its slowest cow.

Retired animals are included, and marked. Her record is the reason the page
exists — an animal that has left the farm is exactly the one somebody looks up
six months later, and hiding her would make the search lie about what the farm
knows.

Read-guarded on Animal.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run

RETIRED = ("Dead", "Deceased", "Sold", "Culled", "Disposed", "Transferred Out")


@frappe.whitelist()
def animal_list():
	def go():
		guard_read("Animal")
		rows = frappe.get_all(
			"Animal",
			fields=["name", "burn_name", "sex", "current_herd", "breed",
			        "date_of_birth", "status", "disabled", "image", "repro_status"],
			order_by="name asc",
			limit_page_length=0,
		)
		return {
			"ok": True,
			"animals": [
				{
					"id": r.name,
					"name": r.burn_name or r.name,
					"sex": r.sex or "Female",
					"herd": r.current_herd or "no herd",
					"breed": r.breed,
					"bornOn": str(r.date_of_birth) if r.date_of_birth else None,
					"status": r.status,
					# The cycle needs her events to resolve properly, which is
					# the profile's job. The list carries the one distinction it
					# can answer cheaply and the page needs to colour a row.
					"stage": "retired" if (r.disabled or r.status in RETIRED) else "open",
					"photo": r.image,
				}
				for r in rows
			],
		}

	return run(go, "livestock animal_list failed")
