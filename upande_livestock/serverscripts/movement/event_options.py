"""What the event screens offer: animals, herds, and who each event may happen to.

Read-guarded on Livestock Event.

`animals` is everyone; the narrowed list beside it is who a calving may
actually be recorded against. It is a separate key rather than a
replacement because the general list still has honest uses — a movement is not a
breeding event — and because a screen that silently swapped its list would leave
nobody able to say why a cow had gone missing from it."""

import frappe

from upande_livestock.serverscripts.common import herd_movement
from upande_livestock.serverscripts.common.choices import (
	active_animals,
	animal_choices,
	herd_label_map,
	select_options,
)
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.event_items import items_by_event


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
			return chosen

		return {
			"ok": True,
			"animals": animal_choices(animals, labels),
			# Cows in calf and near their date.
			"calving_animals": narrowed(herd_movement.calving_candidates()),
			"herds": [{"name": n, "label": l} for n, l in sorted(labels.items(), key=lambda x: x[1])],
			"calving_outcomes": select_options("Livestock Event", "custom_calving_outcome")
			or ["Live Birth", "Still Birth"],
			# What each of this screen's event types may use, by type. One
			# endpoint serves several screens, so a bare list could not say whose.
			# A type the farm mapped nothing to has NO key: absent means "not
			# configured, show nothing", while [] means "mapped, nothing in stock".
			"items_by_event": items_by_event(),
			"employee": current_employee(),
		}

	return run(go, "livestock event_options failed")
