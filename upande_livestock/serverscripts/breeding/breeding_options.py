"""What the breeding screen offers: animals to serve, animals to diagnose, service types.

Read-guarded on Animal."""

import frappe

from upande_livestock.serverscripts.common.choices import active_animals, animal_choices, herd_label_map, select_options
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.stock_items import stock_items
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.common import herd_movement


@frappe.whitelist()
def breeding_options():
	def go():
		guard_read("Animal")

		labels = herd_label_map()
		# Only animals a service can happen to: the top rung of the growth ladder
		# and cows already in milk that are past the post-calving wait. A weaner
		# in the offer list is an invitation to record a service that biology
		# rules out.
		animals = [a for a in active_animals() if herd_movement.is_servable(a.name)]
		sires = sorted(
			{
				r.sire
				for r in frappe.get_all(
					"Livestock Event",
					filters=[["sire", "is", "set"]],
					fields=["sire"],
					limit_page_length=500,
				)
				if r.sire
			}
		)
		return {
			"ok": True,
			"animals": animal_choices(animals, labels),
			"service_herds": herd_movement.service_herds(),
			"service_wait_days": herd_movement.service_wait_days(),
			# Only animals with an open service can be diagnosed — the form's
			# animal list for diagnosis is not the same as the one for service.
			"diagnosis_animals": animal_choices(
				[a for a in active_animals()
				 if a.name in {r["animal"] for r in herd_movement.diagnosable_animals()}],
				labels,
			),
			"service_types": select_options("Livestock Event", "service_type") or ["A.I.", "Natural"],
			"diagnosis_results": select_options("Livestock Event", "diagnosis_result")
			or ["Confirmed", "Not Pregnant", "Aborted"],
			"sires": sires,
			"semen_items": stock_items("semen", livestock_stock.semen_warehouse()),
			"default_semen_item": livestock_stock.default_semen_item(),
			"employee": current_employee(),
		}

	return run(go, "livestock breeding_options failed")
