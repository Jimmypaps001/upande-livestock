# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The metabolic death cause no longer names milk fever.

Rewrites existing Livestock Disposal rows from the old option text to the new
one. Idempotent: a second run finds nothing to change.
"""

import frappe

OLD = "Metabolic (milk fever, ketosis, bloat)"
NEW = "Metabolic (ketosis, bloat)"


def execute():
	frappe.db.sql(
		"UPDATE `tabLivestock Disposal` SET custom_death_cause = %s WHERE custom_death_cause = %s",
		(NEW, OLD),
	)
