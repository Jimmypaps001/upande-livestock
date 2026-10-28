# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Bulls are no longer culled by age: drop the three settings that drove it and
close any open "Bull Cull Due" alert, a kind that is no longer a valid option.

Direct SQL on purpose: the alert kind is no longer in the Select, so loading
the document would fail validation. Idempotent.
"""

import frappe

SETTINGS = ("cull_bulls_after_birth", "bull_cull_max_days", "bull_cull_warn_percent")
KIND = "Bull Cull Due"


def execute():
	for field in SETTINGS:
		frappe.db.delete("Singles", {"doctype": "Livestock Settings", "field": field})
	frappe.db.sql(
		"update `tabLivestock Alert` set status = 'Dismissed' where alert_kind = %s and status = 'Open'",
		(KIND,),
	)
	frappe.clear_cache(doctype="Livestock Settings")
