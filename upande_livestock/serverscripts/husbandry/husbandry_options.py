"""What the husbandry screen offers: the routine event types and their targets.

Read-guarded on Livestock Event."""

import frappe

from upande_livestock.serverscripts.common.choices import active_animals, animal_choices, herd_choices, herd_label_map
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.stock_items import stock_items
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.husbandry._shared import DRUG_CONSUMING_TYPES, HUSBANDRY_TYPES


@frappe.whitelist()
def husbandry_options():
	def go():
		guard_read("Livestock Event")
		labels = herd_label_map()
		return {
			"ok": True,
			"animals": animal_choices(active_animals(), labels),
			"event_types": list(HUSBANDRY_TYPES),
			"drug_consuming_types": list(DRUG_CONSUMING_TYPES),
			# No warehouse: every configured drug store is searched, and each
			# choice says which one its stock is in. The single setting named
			# a store with no Bin rows at all on live.
			"drug_items": stock_items("drug"),
			"drug_warehouses": livestock_stock.drug_source_warehouses(),
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
