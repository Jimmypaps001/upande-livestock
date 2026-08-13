# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Retire animals that were already culled before Animal.disabled existed.

Without this, historical culls stay pickable in link fields while new ones do
not — the same animal treated two different ways depending on when it left.
"""

import frappe

RETIRED_STATUSES = ("Sold", "Dead", "Culled", "Transferred Out")


def execute():
	if not frappe.db.has_column("Animal", "disabled"):
		return

	frappe.db.sql(
		"""UPDATE `tabAnimal`
		   SET disabled = 1
		   WHERE IFNULL(disabled, 0) = 0
		     AND status IN %(statuses)s""",
		{"statuses": RETIRED_STATUSES},
	)
	frappe.db.commit()
