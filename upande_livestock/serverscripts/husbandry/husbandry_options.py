"""What the husbandry screen offers: the routine event types and their targets.

Read-guarded on Livestock Event."""

import frappe

from upande_livestock.serverscripts.common.choices import active_animals, animal_choices, herd_choices, herd_label_map
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.husbandry._shared import HUSBANDRY_TYPES, _type_consumes_drugs, husbandry_drug_items, husbandry_items_mapped


@frappe.whitelist()
def husbandry_options():
	def go():
		guard_read("Livestock Event")
		labels = herd_label_map()
		return {
			"ok": True,
			"animals": animal_choices(active_animals(), labels),
			"event_types": list(HUSBANDRY_TYPES),
			"drug_consuming_types": [t for t in HUSBANDRY_TYPES if _type_consumes_drugs(t)],
			# The groups the farm mapped to these events, searched across every
			# warehouse of its company. The old two-kind lookup asked one group
			# named by a constant, in stores somebody had typed — and on live
			# that returned nothing while 74 stocked drug bins sat elsewhere.
			"drug_items": husbandry_drug_items(),
			# [] above is unmapped OR unstocked; this says which.
			"drug_items_mapped": husbandry_items_mapped(),
			"drug_warehouse": livestock_stock.drug_warehouse(),
			"herds": herd_choices(),
			"warehouses": [
				w.name
				for w in frappe.get_all(
					"Warehouse",
					filters={"is_group": 0, "disabled": 0},
					fields=["name"],
					order_by="name asc",
					limit_page_length=500,
				)
			],
			"employee": current_employee(),
		}

	return run(go, "livestock husbandry_options failed")
