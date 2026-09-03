# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Everything the app needs before it can show a form, in one call.

Every record screen on the handset needs the same few things: who the operator
is, which herds exist, what the farm's timing settings say, which company to
book against, and what the drug and semen stores actually hold. The app was
fetching those per screen — `useOperator` on eight screens, `useHerds` on five,
`useDefaultCompany` on four, `useLivestockSettings` on three — and
`useStoreQty` made one request *per item per warehouse*, so opening the service
form cost a request for every semen straw on the shelf.

That is the shape `upande_scp.serverscripts.mobile.get_farm_data_bundle` was
built to fix, and this is the same fix: one response, one round-trip, with a
`version` the client sends back to skip the payload entirely when nothing has
moved.

Read-guarded on Herds. It discloses herd structure, store balances and the
farm's settings — not something an arbitrary logged-in user should collect.
"""

import frappe

from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.common.choices import herd_label_map, select_options
from upande_livestock.serverscripts.common.company import default_company
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.stock_items import stock_items
from upande_livestock.serverscripts.mobile._shared import digest, unchanged

# The doctypes whose state this payload reflects. A change to any of them must
# change the version, or the phone will keep serving a stale form.
_SOURCES = ["Herds", "Livestock Event Type", "Employee", "Bin", "Item"]


@frappe.whitelist()
def get_bootstrap_bundle(version=None):
	def go():
		guard_read("Herds")
		current = digest(_SOURCES)
		if unchanged(version, current):
			return {"ok": True, "unchanged": True, "version": current}

		drug_wh = livestock_stock.drug_warehouse()
		semen_wh = livestock_stock.semen_warehouse()
		labels = herd_label_map()

		herds = frappe.get_all(
			"Herds",
			fields=[
				"name",
				"herd_name",
				"number_of_animals",
				"bom",
				"custom_herd_category",
				"custom_is_milking",
				"custom_is_dry",
				"custom_is_calf_rearing",
				"min_age",
				"max_age",
			],
			order_by="herd_name asc",
		)
		return {
			"ok": True,
			"version": current,
			"operator": current_employee(),
			"company": default_company(),
			"warehouses": {"drug": drug_wh, "semen": semen_wh},
			"herds": [
				{
					"name": h.name,
					"label": labels.get(h.name, h.name),
					"heads": int(h.number_of_animals or 0),
					"category": h.custom_herd_category,
					"is_milking": bool(h.custom_is_milking),
					"is_dry": bool(h.custom_is_dry),
					"is_calf_rearing": bool(h.custom_is_calf_rearing),
					"min_age": h.min_age,
					"max_age": h.max_age,
					"has_bom": bool(h.bom),
				}
				for h in herds
			],
			"event_types": frappe.get_all(
				"Livestock Event Type",
				filters={"is_active": 1},
				fields=["name", "creates_animal", "detail_doctype"],
				order_by="name asc",
			),
			# The N+1 this bundle exists to remove: every issuable item with its
			# on-hand quantity, for the store the issue will actually draw from.
			"drugs": stock_items("drug", drug_wh),
			"semen": stock_items("semen", semen_wh),
			"options": {
				"service_types": select_options("Livestock Event", "service_type"),
				"diagnosis_results": select_options("Livestock Event", "diagnosis_result"),
				"calving_outcomes": select_options("Livestock Event", "custom_calving_outcome"),
				"abortion_causes": select_options("Livestock Event", "abortion_cause"),
				"animal_sexes": select_options("Animal", "sex"),
			},
		}

	return run(go, "livestock mobile get_bootstrap_bundle failed")
