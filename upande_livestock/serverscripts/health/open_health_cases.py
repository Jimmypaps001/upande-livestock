"""The cases still needing attention.

Read-guarded on Livestock Health Case."""

import frappe

from upande_livestock.serverscripts.common.choices import select_options
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.stock_items import stock_items
from upande_livestock.serverscripts.common import stock as livestock_stock


@frappe.whitelist()
def open_health_cases():
	"""Cases still being treated, for the treatment form's case picker."""

	def go():
		guard_read("Livestock Health Case")
		rows = frappe.get_all(
			"Livestock Health Case",
			filters={"docstatus": 1, "case_status": ["!=", "Closed"]},
			fields=["name", "animal", "animal_name", "case_status", "opened_date", "provisional_diagnosis"],
			order_by="opened_date desc",
			limit_page_length=200,
		)
		return {
			"ok": True,
			"cases": [
				{
					"value": r.name,
					"label": "{0} · {1}{2}".format(
						r.name,
						r.animal_name or r.animal,
						" · " + r.provisional_diagnosis if r.provisional_diagnosis else "",
					),
					"animal": r.animal,
				}
				for r in rows
			],
			"drug_items": stock_items("drug", livestock_stock.drug_warehouse()),
			"routes": select_options("Livestock Health Treatment", "route"),
			"employee": current_employee(),
		}

	return run(go, "livestock open_health_cases failed")
