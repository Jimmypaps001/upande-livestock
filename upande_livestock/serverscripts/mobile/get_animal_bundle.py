# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The animal picker's data, in one call rather than one per screen.

Every record screen opens with an animal picker, and the phone works offline in
a shed with no signal, so the list has to be on the device before the operator
walks out. This returns the active herd in one payload, keyed for local search,
with the same `version` skip as the bootstrap bundle.

Scoped by `herd` when the screen already knows it — a whole-herd vaccination
does not need all 331 animals — and capped, because a picker that has to render
thousands of rows is the wrong interface anyway.

"Active" is `common.choices.active_animals`, the same predicate the desk
dropdowns use. The phone must not carry its own idea of which animals still
count, which is exactly how the dashboard came to show animals that had left
the farm.

Read-guarded on Animal.
"""

import frappe

from upande_livestock.serverscripts.common.choices import (
	ANIMAL_FIELDS,
	RETIRED_STATUSES,
	animal_label,
	herd_label_map,
)
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.mobile._shared import digest, unchanged

_SOURCES = ["Animal", "Herds"]
_CAP = 2000


@frappe.whitelist()
def get_animal_bundle(herd=None, version=None):
	def go():
		guard_read("Animal")
		current = digest(_SOURCES) + (f":{herd}" if herd else "")
		if unchanged(version, current):
			return {"ok": True, "unchanged": True, "version": current}

		filters = [["status", "not in", RETIRED_STATUSES], ["disabled", "=", 0]]
		if herd:
			filters.append(["current_herd", "=", herd])
		rows = frappe.get_all(
			"Animal",
			filters=filters,
			fields=[*ANIMAL_FIELDS, "sex", "status", "date_of_birth"],
			order_by="tag_number asc",
			limit_page_length=_CAP,
		)
		labels = herd_label_map()
		return {
			"ok": True,
			"version": current,
			"herd": herd,
			"capped": len(rows) >= _CAP,
			"animals": [
				{
					"name": r.name,
					"label": animal_label(r),
					"tag": r.tag_number,
					"burn_name": r.burn_name,
					"herd": r.current_herd,
					"herd_label": labels.get(r.current_herd, r.current_herd),
					"sex": r.sex,
					"status": r.status,
					"repro_status": r.repro_status,
					"date_of_birth": r.date_of_birth,
				}
				for r in rows
			],
		}

	return run(go, "livestock mobile get_animal_bundle failed")
