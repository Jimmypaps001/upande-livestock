# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Stamp the herds' own BOMs as their standing ration.

`Herds.bom` already IS the standing ration; this patch just makes that fact
readable from the BOM side too — ``custom_is_livestock_feed = 1``,
``custom_ration_kind = "Standing"``, and ``custom_herd`` pointing back at the
herd.

Two of today's BOMs are each the standing ration for *two* herds at once
(TMR Calves Meal for both 0-2 and 2-4; Dry/Steamers/Incalf Heifers for both
INCALF HEIFERS and STEAMERS). ``custom_herd`` is a single Link and cannot
hold both, so a shared BOM is attributed to whichever herd was actually FED
it first: the Livestock Event timeline (event_type = "Feeding") says which
herd's trough that item first went into, which is a fact, not a guess. Ties
on the same ``event_date`` break on the event's ``creation`` — whichever was
entered first is what actually happened first, as best the record shows.

If neither herd sharing the BOM has ever been fed it, there is nothing to go
on: "fed first" has no answer, and a blank ``custom_herd`` stays more honest
than picking one. It is still marked livestock feed / Standing either way.
Anyone asking "what is herd X's standing ration" reads ``Herds.bom`` directly
— unambiguous regardless, and untouched by this patch either way.
"""

import frappe


def _first_fed_herd(item, herds):
	"""Of `herds`, whichever has the earliest submitted Feeding event whose
	Stock Entry issued `item` — i.e. whichever trough this ration's item
	actually landed in first. None if neither herd has ever been fed it.

	A single query ordered by (event_date, creation) and limited to one row
	is the tiebreak: the smallest row overall must belong to whichever herd's
	own earliest occurrence is smallest, so there is no need to aggregate per
	herd first. `creation` is the tiebreaker for two herds first fed on the
	same date — it records which was actually entered first.
	"""
	if not herds:
		return None
	rows = frappe.db.sql(
		"""
		SELECT le.current_herd AS herd
		FROM `tabLivestock Event` le
		INNER JOIN `tabStock Entry Detail` sed ON sed.parent = le.stock_entry
		WHERE le.event_type = 'Feeding'
		  AND le.docstatus = 1
		  AND le.current_herd IN %(herds)s
		  AND sed.item_code = %(item)s
		ORDER BY le.event_date ASC, le.creation ASC
		LIMIT 1
		""",
		{"herds": herds, "item": item},
		as_dict=True,
	)
	return rows[0].herd if rows else None


def execute():
	if not frappe.db.has_column("BOM", "custom_herd"):
		return

	herd_by_bom = {}
	for row in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"]):
		herd_by_bom.setdefault(row.bom, []).append(row.name)

	for bom_name, herds in herd_by_bom.items():
		if not frappe.db.exists("BOM", bom_name):
			continue
		if len(herds) == 1:
			herd = herds[0]
		else:
			item = frappe.db.get_value("BOM", bom_name, "item")
			herd = _first_fed_herd(item, herds)

		values = {
			"custom_herd": herd,
			"custom_is_livestock_feed": 1,
			"custom_ration_kind": "Standing",
		}
		for fieldname, value in values.items():
			frappe.db.set_value("BOM", bom_name, fieldname, value, update_modified=False)

	frappe.db.commit()
