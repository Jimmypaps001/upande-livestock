# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Let the people who run the feed store see the items in it.

No Livestock role could read Item. That went unnoticed because the two people
who exercised the app hold Stock User and Stock Manager as well — roles that
have nothing to do with livestock — so the gap only shows on a user who holds
the livestock roles and nothing else, which is exactly what a farm hand is.

What it broke: `feeding.concentrate_plan`, the week's mixing list and the farm's
concentrate stock, and `husbandry.drugs_in_store`, which the drug picker on the
husbandry, check-up and treatment screens is built from. Both guard on Item
read, correctly — they disclose item names and stock balances, and that is Item
and Bin data whatever screen it is drawn on. So the guard was right and the role
was wrong.

READ ONLY, for every livestock role. It was first written for Stores and
Manager alone, on the reasoning that a vet has no business in the item master.
That was wrong: `drugs_in_store` guards Item read too, and it is what the drug
picker is built from — so a vet recording a treatment, and an attendant or
breeder recording a vaccination, hit exactly the same wall. Splitting hairs over
which of six field roles may *see* a list of items buys nothing and costs a
support call every time somebody is handed the wrong pair.

What is worth withholding is writing. Nothing here grants write, create, delete,
submit or report: an item is created by whoever buys it, not by whoever feeds,
treats or milks against it.

Item is a core doctype, so this lands as a Custom DocPerm rather than editing
the shipped permissions. Idempotent: a role that already has the read is left
alone, including one a person granted by hand.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

DOCTYPE = "Item"
ROLES = (
	"Livestock Manager",
	"Livestock Stores",
	"Livestock Vet",
	"Livestock Attendant",
	"Livestock Breeder",
	"Livestock Milker",
)


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	for role in ROLES:
		if not frappe.db.exists("Role", role):
			# The roles are created by the doctype permissions this app ships;
			# a site that has not migrated them yet gets this on its next run.
			print(f"[livestock-item-read] {role} does not exist yet — skipped")
			continue
		if frappe.db.exists(
			"Custom DocPerm", {"parent": DOCTYPE, "role": role, "permlevel": 0}
		) or frappe.db.exists("DocPerm", {"parent": DOCTYPE, "role": role, "permlevel": 0}):
			print(f"[livestock-item-read] {role} already has a permission row on {DOCTYPE}")
			continue

		add_permission(DOCTYPE, role, 0)
		# add_permission grants read; every other right is switched off
		# explicitly rather than trusted to default, so a change to that default
		# cannot quietly widen this.
		update_permission_property(DOCTYPE, role, 0, "read", 1)
		for right in ("write", "create", "delete", "submit", "cancel", "amend", "report", "export"):
			update_permission_property(DOCTYPE, role, 0, right, 0)
		print(f"[livestock-item-read] {role} may now read {DOCTYPE}")

	frappe.clear_cache()
	frappe.db.commit()
