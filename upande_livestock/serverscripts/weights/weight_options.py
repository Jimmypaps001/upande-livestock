"""What the weighing screen offers: animals, methods and the operator.

Read-guarded on Livestock Weight Record."""

import frappe

from upande_livestock.serverscripts.common.choices import (
	active_animals,
	animal_choices,
	herd_choices,
	herd_label_map,
	select_options,
)
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def weight_options():
	def go():
		guard_read("Livestock Weight Record")
		labels = herd_label_map()
		return {
			"ok": True,
			"animals": animal_choices(active_animals(), labels),
			# Weighing is a race through a crush as often as it is one cow on a
			# scale, so the screen can fill its list in from a herd.
			"herds": herd_choices(),
			"methods": select_options("Livestock Weight Record", "method"),
			"employee": current_employee(),
		}

	return run(go, "livestock weight_options failed")
