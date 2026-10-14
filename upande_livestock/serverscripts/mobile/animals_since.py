# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The phone's own copy of the herd, kept current by deltas.

`get_animal_bundle` answers "who is on the farm" for one picker. This is the
other half of the offline store: the phone keeps every active animal in SQLite,
asks once for all of them on login, and afterwards asks only for what changed
since the `server_time` it was last given.

`since=None` is the full set of active animals. With `since`, `animals` holds
the active animals modified after it and `removed` the names that stopped being
active in that time: retired (disabled, or a retired status) or deleted
outright. A phone applies both in one transaction, so a disposal reaches the
shed the next time the app wakes rather than lingering in a picker.

`server_time` is read BEFORE the queries. An animal saved while they run is then
sent again by the next delta instead of falling in the gap between the two.

One query for the animals and one each for the removals. No per-row `get_doc`:
at 300 animals that is the difference between one round-trip and a minute.

The fields are the ones the Animals page's portrait shows (see
`animals/animal_profile`): her picture, age, breed, herd, sex, dam and sire. The
stage ("Fresh", "In calf") is worked out from her event history and stays with
`animal_profile`; the phone asks for it when it is online.

Read-guarded on Animal.
"""

import frappe
from frappe.utils import now

from upande_livestock.serverscripts.common import animal_stage
from upande_livestock.serverscripts.common.choices import RETIRED_STATUSES
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def animals_since(since=None):
	def go():
		guard_read("Animal")
		server_time = now()
		since_ts = (since or "").strip() or None

		active = [["status", "not in", RETIRED_STATUSES], ["disabled", "=", 0]]
		filters = list(active)
		or_filters = None
		if since_ts:
			moved = sorted(animal_stage.moved_since(since_ts))
			or_filters = [["modified", ">", since_ts]]
			if moved:
				or_filters.append(["name", "in", moved])
		rows = frappe.get_all(
			"Animal",
			filters=filters,
			or_filters=or_filters,
			fields=["name", "disabled", "tag_number", "burn_name", "sex", "breed", "date_of_birth",
			        "current_herd", "status", "repro_status", "image", "dam",
			        "sire_name", "parity", "last_weight_kg", "modified"],
			order_by="tag_number asc",
			limit_page_length=0,
		)

		stages = animal_stage.stages_for(rows)

		removed = []
		if since_ts:
			gone = frappe.get_all(
				"Animal",
				or_filters=[["disabled", "=", 1], ["status", "in", RETIRED_STATUSES]],
				filters=[["modified", ">", since_ts]],
				pluck="name",
				limit_page_length=0,
			)
			deleted = frappe.get_all(
				"Deleted Document",
				filters={"deleted_doctype": "Animal", "creation": [">", since_ts]},
				pluck="deleted_name",
				limit_page_length=0,
			)
			removed = sorted(set(gone) | set(deleted))

		return {
			"ok": True,
			"server_time": server_time,
			"full": since_ts is None,
			"animals": [
				{
					"name": r.name,
					"tag": r.tag_number,
					"animal_name": r.burn_name,
					"sex": r.sex,
					"breed": r.breed,
					"dob": r.date_of_birth,
					"herd": r.current_herd,
					"status": r.status,
					"stage": stages[r.name],
					"repro_status": r.repro_status,
					"image": r.image,
					"dam": r.dam,
					"sire": r.sire_name,
					"parity": r.parity,
					"last_weight_kg": r.last_weight_kg,
					"modified": r.modified,
				}
				for r in rows
			],
			"removed": removed,
		}

	return run(go, "livestock mobile animals_since failed")
