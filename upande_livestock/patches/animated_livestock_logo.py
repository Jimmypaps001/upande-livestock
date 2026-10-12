# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Point the Livestock apps-screen tile at the animated mark (livestock_logo.svg).

The ``Desktop Icon`` row is created on the site by Frappe from
``add_to_apps_screen`` and keeps the logo it was made with, so the hooks change
alone does not reach existing sites. Only Livestock's own old logo path is
touched — another app's tile that happens to use an Upande PNG is left alone.
Idempotent.
"""

import frappe

OLD = "/assets/upande_livestock/images/upande_logo.png"
NEW = "/assets/upande_livestock/images/livestock_logo.svg"


def execute():
	if not frappe.db.table_exists("Desktop Icon") or not frappe.db.has_column("Desktop Icon", "logo_url"):
		return
	frappe.db.sql("UPDATE `tabDesktop Icon` SET logo_url = %s WHERE logo_url = %s", (NEW, OLD))
	frappe.clear_cache()
