# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Drop the Livestock Disposal columns nothing ever set.

`gain_loss`, `income_account`, `disposal_account` and `cost_center` were on the
form but read and written by nothing: the sale and the write-off resolve their
own accounts and cost centre from the Company and the Asset Category. Empty on
every disposal on every site checked.
"""

import frappe

DROPPED = ("gain_loss", "income_account", "disposal_account", "cost_center")


def execute():
	frappe.db.delete("Property Setter", {"doc_type": "Livestock Disposal", "field_name": ("in", DROPPED)})
	frappe.clear_cache(doctype="Livestock Disposal")
	for column in DROPPED:
		if frappe.db.has_column("Livestock Disposal", column):
			frappe.db.sql_ddl(f"ALTER TABLE `tabLivestock Disposal` DROP COLUMN `{column}`")
