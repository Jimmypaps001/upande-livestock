# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Flag the event types that take drugs out of a store.

`Livestock Event Type.consumes_drugs` replaces a hardcoded ("Vaccination",
"Deworming") tuple, so the farm can flag a new drug-consuming type — dry-cow
therapy at Drying Off, calcium at Calving — without a deploy. This sets the ones
that were already true in code, plus the two the block now collects drugs for.

Service is deliberately absent: it consumes a semen straw through its own field,
not the drug table.
"""

import frappe

CONSUMING = ("Vaccination", "Deworming", "Check Up", "Drying Off")


def execute():
	if not frappe.db.has_column("Livestock Event Type", "consumes_drugs"):
		return
	for name in CONSUMING:
		if frappe.db.exists("Livestock Event Type", name):
			frappe.db.set_value("Livestock Event Type", name, "consumes_drugs", 1, update_modified=False)
