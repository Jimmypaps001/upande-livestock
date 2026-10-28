# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Livestock Quality role, for the person who files lab results.

The role is also created by Milk Recording's permission rows when the doctype
syncs; this makes it exist even on a site that synced them first. Grants come
from the DocType schema, not here. Idempotent.
"""

import frappe


def execute():
	if frappe.db.exists("Role", "Livestock Quality"):
		return
	frappe.get_doc(
		{"doctype": "Role", "role_name": "Livestock Quality", "desk_access": 1, "is_custom": 0}
	).insert(ignore_permissions=True)
