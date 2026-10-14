# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The vets a screen may offer: enabled Livestock Vet records.

Few enough to list outright (a farm has a handful, internal and contracted), so
the whole set is returned and the screen filters it. `mine` is the signed-in
user's own vet record, for the picker's default.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.upande_livestock.doctype.livestock_vet.livestock_vet import vet_for_user


def vet_rows():
	rows = frappe.get_all(
		"Livestock Vet",
		filters={"enabled": 1},
		fields=["name", "vet_name", "vet_type", "practice_name", "registration_number", "licence_expiry"],
		order_by="vet_name asc",
		limit=500,
	)
	return [
		{
			"value": r.name,
			"label": r.vet_name or r.name,
			"type": r.vet_type,
			"detail": " · ".join(
				x for x in (r.vet_type, r.practice_name if r.vet_type == "External" else None) if x
			),
		}
		for r in rows
	]


@frappe.whitelist()
def vet_options(payload=None):
	def go():
		guard_read("Livestock Vet")
		return {"ok": True, "mine": vet_for_user(), "vets": vet_rows()}

	return run(go, "livestock vet_options failed")
