# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The "Upande Livestock" module belongs to this app.

On the live site the module was created in the desk before the app existed,
so its Module Def names "frappe" as its app. Frappe decides which app owns a
doctype — what to export it to, what counts as an orphan — through that
record, so it is claimed before anything else runs.
"""

import frappe

MODULE = "Upande Livestock"


def execute():
	if frappe.db.exists("Module Def", MODULE):
		frappe.db.set_value("Module Def", MODULE, {"app_name": "upande_livestock", "custom": 0},
		                    update_modified=False)
	frappe.clear_cache()
