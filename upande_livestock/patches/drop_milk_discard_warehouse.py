# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Milk Recording's per-record discard store was never set, on any site.

No screen sends it and no record carries one; the discard store is Livestock
Settings' custom_milk_discard_warehouse, which is what every recording used.
"""

import frappe


def execute():
	frappe.db.delete("Property Setter", {"doc_type": "Milk Recording", "field_name": "discard_warehouse"})
	frappe.clear_cache(doctype="Milk Recording")
	if frappe.db.has_column("Milk Recording", "discard_warehouse"):
		frappe.db.sql_ddl("ALTER TABLE `tabMilk Recording` DROP COLUMN `discard_warehouse`")
