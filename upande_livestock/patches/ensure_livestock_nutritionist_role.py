# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Livestock Nutritionist role, and what it may touch outside this app.

Ported from Kaitet's Livestock Quality role; Mutara uses it for the person who
balances feed: they keep the nutrient figures on Livestock Feed and design the
herds' rations and concentrates in the Ration Editor.

The app's own doctypes grant it through their schema (Livestock Feed: write;
Herds and Livestock Settings: read). The ERPNext doctypes it needs are core, so
they land here as Custom DocPerms:

* BOM read + create — a ration or concentrate IS a BOM, and saving one is
  guarded on BOM create (`set_herd_ration`, `set_concentrate`). The insert and
  submit themselves run with ignore_permissions, so no submit right is given:
  the role cannot submit or cancel a BOM from the desk.
* Item read — the feed library and the store balances name items.
* Work Order read — the Rations page lists what each herd was actually fed.

Nothing that moves stock: no Work Order create, no Stock Entry. Mixing and
issuing stay with Livestock Stores and the Manager.

Idempotent: a role/doctype pair that already has a permission row (including
one granted by hand) is left alone.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

ROLE = "Livestock Nutritionist"

GRANTS = {
	"BOM": ("read", "create"),
	"Item": ("read",),
	"Work Order": ("read",),
}

OTHER_RIGHTS = ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export")


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc(
			{"doctype": "Role", "role_name": ROLE, "desk_access": 1, "is_custom": 0}
		).insert(ignore_permissions=True)

	for doctype, rights in GRANTS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		if frappe.db.exists(
			"Custom DocPerm", {"parent": doctype, "role": ROLE, "permlevel": 0}
		) or frappe.db.exists("DocPerm", {"parent": doctype, "role": ROLE, "permlevel": 0}):
			continue
		add_permission(doctype, ROLE, 0)
		# Every right set explicitly, so a change to add_permission's defaults
		# cannot quietly widen this.
		for right in OTHER_RIGHTS:
			update_permission_property(doctype, ROLE, 0, right, 1 if right in rights else 0)

	frappe.clear_cache()
	frappe.db.commit()
