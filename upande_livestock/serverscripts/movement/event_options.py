"""What the event screens offer: animals, herds, and who each event may happen to.

Read-guarded on Livestock Event.

`animals` is everyone; the two narrowed lists beside it are who a drying off and
a calving may actually be recorded against. They are separate keys rather than a
replacement because the general list still has honest uses — a movement is not a
breeding event — and because a screen that silently swapped its list would leave
nobody able to say why a cow had gone missing from it."""

import frappe

from upande_livestock.serverscripts.common.choices import active_animals, animal_choices, herd_label_map, select_options
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common import herd_movement


@frappe.whitelist()
def event_options():
	def go():
		guard_read("Livestock Event")
		labels = herd_label_map()
		animals = active_animals()
		by_name = {a.name: a for a in animals}

		def narrowed(rows):
			"""The eligibility rows as picker choices, in the order they came.

			Order is the message on both lists — nearest to calving first — so it
			is preserved rather than re-sorted alphabetically by the label maker.
			"""
			picked = [by_name[r["animal"]] for r in rows if r["animal"] in by_name]
			chosen = animal_choices(picked, labels)
			extra = {r["animal"]: r for r in rows}
			for choice in chosen:
				row = extra.get(choice["name"], {})
				choice["due"] = row.get("due")
				choice["days_to_calving"] = row.get("days_to_calving")
				choice["ready"] = bool(row.get("ready"))
				if "dried_off" in row:
					choice["dried_off"] = row["dried_off"]
			return chosen

		return {
			"ok": True,
			"animals": animal_choices(animals, labels),
			# Cows in calf, still in milk, and inside the farm's dry-off window.
			"dry_off_animals": narrowed(herd_movement.dry_off_candidates()),
			# Cows in calf, dried off, and near their date.
			"calving_animals": narrowed(herd_movement.calving_candidates()),
			# Where the farm says a dried-off cow goes. The screen offers it and
			# warns about anything else rather than refusing it.
			"dry_off_herd": herd_movement.dry_off_destination()["herd"],
			"herds": [{"name": n, "label": l} for n, l in sorted(labels.items(), key=lambda x: x[1])],
			"calving_outcomes": select_options("Livestock Event", "custom_calving_outcome")
			or ["Live Birth", "Still Birth"],
			"employee": current_employee(),
		}

	return run(go, "livestock event_options failed")
