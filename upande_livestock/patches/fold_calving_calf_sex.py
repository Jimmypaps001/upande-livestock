# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A Calving no longer records the calf's sex; each Birth records its own.

`custom_calf_sex` on a Calving could only hold one answer, so twins had none,
and it repeated what the calf's Birth already says. Nothing read it.

Older sites booked calvings before Births existed as their own events: the
live site has fourteen calvings carrying a sex and five births. Where no
Birth linked to the calving names the calf's sex, the value is written into
the calving's remarks before the column goes, so it is not lost.
"""

import frappe

MARKER = "[migrated] Calf sex:"


def execute():
	if not frappe.db.has_column("Livestock Event", "custom_calf_sex"):
		return

	rows = frappe.db.sql(
		"""SELECT c.name, c.remarks, c.custom_calf_sex
		   FROM `tabLivestock Event` c
		   WHERE c.event_type = 'Calving'
		     AND IFNULL(c.custom_calf_sex, '') <> ''
		     AND NOT EXISTS (
		         SELECT 1 FROM `tabLivestock Event` b
		         WHERE b.event_type = 'Birth' AND b.related_calving = c.name
		           AND IFNULL(b.calf_sex, '') <> '')""",
		as_dict=True,
	)
	for row in rows:
		if MARKER in (row.remarks or ""):
			continue
		note = f"{MARKER} {row.custom_calf_sex}"
		remarks = f"{row.remarks}\n{note}" if row.remarks else note
		frappe.db.set_value("Livestock Event", row.name, "remarks", remarks, update_modified=False)

	frappe.db.delete("Custom Field", {"dt": "Livestock Event", "fieldname": "custom_calf_sex"})
	frappe.db.delete("Property Setter", {"doc_type": "Livestock Event", "field_name": "custom_calf_sex"})
	frappe.clear_cache(doctype="Livestock Event")
	frappe.db.sql_ddl("ALTER TABLE `tabLivestock Event` DROP COLUMN `custom_calf_sex`")
