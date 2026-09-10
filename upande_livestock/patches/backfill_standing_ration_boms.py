# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Stamp the herds' own BOMs as their standing ration.

`Herds.bom` already IS the standing ration; this patch just makes that fact
readable from the BOM side too — ``custom_is_livestock_feed = 1``,
``custom_ration_kind = "Standing"``, and (where unambiguous)
``custom_herd`` pointing back at the herd.

Two of today's BOMs are each the standing ration for *two* herds at once
(TMR Calves Meal for both 0-2 and 2-4; Dry/Steamers/Incalf Heifers for both
INCALF HEIFERS and STEAMERS). ``custom_herd`` is a single Link and cannot
hold both, and picking one (first, last, whichever) would make a future
"what recipes has herd X had" query lie for the herd left out — it would
look as if that herd never had this BOM, when ``Herds.bom`` says otherwise.
So a shared BOM is still marked livestock feed / Standing, but its
``custom_herd`` is left blank rather than guessed. Anyone asking "what is
herd X's standing ration" reads ``Herds.bom`` directly, which is unambiguous
either way and untouched by this patch.
"""

import frappe


def execute():
	if not frappe.db.has_column("BOM", "custom_herd"):
		return

	herd_by_bom = {}
	for row in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"]):
		herd_by_bom.setdefault(row.bom, []).append(row.name)

	for bom_name, herds in herd_by_bom.items():
		if not frappe.db.exists("BOM", bom_name):
			continue
		values = {
			"custom_is_livestock_feed": 1,
			"custom_ration_kind": "Standing",
		}
		if len(herds) == 1:
			values["custom_herd"] = herds[0]
		for fieldname, value in values.items():
			frappe.db.set_value("BOM", bom_name, fieldname, value, update_modified=False)

	frappe.db.commit()
