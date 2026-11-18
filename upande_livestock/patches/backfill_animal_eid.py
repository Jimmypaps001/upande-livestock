# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Fill Animal.eid from a tag number that is an electronic ear tag.

Mutara's animals were migrated with the RFID the scale reads (982 091086140137)
as their tag number and the visual tag (MOL876, 51C) as their burn name. The
Gallagher import matches on the EID, so it is copied into its own field where
the tag number is plainly one: fifteen digits, with or without the space after
the country code. Nothing is overwritten.
"""

import re

import frappe

EID = re.compile(r"^\d{3} ?\d{12}$")


def execute():
	if not frappe.db.has_column("Animal", "eid"):
		return
	rows = frappe.db.sql(
		"select name, tag_number from `tabAnimal` where ifnull(eid, '') = ''", as_dict=True
	)
	for row in rows:
		tag = (row.tag_number or "").strip()
		if EID.match(tag):
			frappe.db.set_value("Animal", row.name, "eid", tag, update_modified=False)
	frappe.db.commit()
