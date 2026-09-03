"""What the event screen offers: animals, herds and the calving outcomes.

Read-guarded on Livestock Event."""

import frappe

from upande_livestock.serverscripts.common.choices import active_animals, animal_choices, herd_label_map, select_options
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def event_options():
	def go():
		guard_read("Livestock Event")
		labels = herd_label_map()
		animals = active_animals()
		return {
			"ok": True,
			"animals": animal_choices(animals, labels),
			"herds": [{"name": n, "label": l} for n, l in sorted(labels.items(), key=lambda x: x[1])],
			"calving_outcomes": select_options("Livestock Event", "custom_calving_outcome")
			or ["Live Birth", "Still Birth"],
			"employee": current_employee(),
		}

	return run(go, "livestock event_options failed")
