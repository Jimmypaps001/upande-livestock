# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""`incalf_general_days` was a Livestock Settings knob that nothing read."""

import frappe


def execute():
	frappe.db.delete("Singles", {"doctype": "Livestock Settings", "field": "incalf_general_days"})
	frappe.clear_cache(doctype="Livestock Settings")
