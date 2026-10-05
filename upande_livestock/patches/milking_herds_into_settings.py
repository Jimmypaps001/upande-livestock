# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which herds are milked is a list on Livestock Settings, not a box on each Herd.

Herds carried "Is Milking Herd" and "Is Dry / Pre-calving Herd" boxes; the
lactation logic read Livestock Settings' high- and low-yield herds instead, and
only the phone read the boxes. The live site ticks three herds as milking and
sets no high/low-yield herd at all, so the two answers already disagreed.

The table is filled from what the site says today — every herd ticked as
milking, then the high- and low-yield herds — unless the farm has already
filled it. Dry herds are Settings' drying-off and steamer herds, which the
code already used; the box is dropped without being copied.
"""

import frappe

from upande_livestock.patches._fold import column_exists, drop_column

SETTINGS = "Livestock Settings"


def execute():
	settings = frappe.get_single(SETTINGS)
	if not settings.meta.has_field("milking_herds"):
		return
	if not settings.get("milking_herds"):
		herds = []
		if column_exists("Herds", "custom_is_milking"):
			herds += frappe.db.sql_list(
				"SELECT name FROM `tabHerds` WHERE IFNULL(custom_is_milking, 0) = 1 ORDER BY name"
			)
		herds += [settings.get("high_yield_herd"), settings.get("low_yield_herd")]
		for herd in dict.fromkeys(h for h in herds if h and frappe.db.exists("Herds", h)):
			settings.append("milking_herds", {"herd": herd})
		if settings.get("milking_herds"):
			settings.flags.ignore_validate = True
			settings.flags.ignore_mandatory = True
			settings.save(ignore_permissions=True)

	for column in ("custom_is_milking", "custom_is_dry"):
		frappe.db.delete("Custom Field", {"dt": "Herds", "fieldname": column})
		frappe.db.delete("Property Setter", {"doc_type": "Herds", "field_name": column})
		drop_column("Herds", column)
	frappe.clear_cache(doctype="Herds")
