"""What the disposal screen offers: animals, disposal types and customers.

Read-guarded on Livestock Disposal."""

import frappe

from upande_livestock.serverscripts.common.choices import active_animals, animal_choices, herd_label_map, select_options
from upande_livestock.serverscripts.common.company import default_company
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def disposal_options():
	def go():
		guard_read("Livestock Disposal")
		labels = herd_label_map()
		return {
			"ok": True,
			"animals": animal_choices(active_animals(), labels),
			"disposal_types": select_options("Livestock Disposal", "disposal_type"),
			"customers": [
				c.name
				for c in frappe.get_all(
					"Customer", fields=["name"], order_by="name asc", limit_page_length=500
				)
			],
			"company": default_company(),
		}

	return run(go, "livestock disposal_options failed")
