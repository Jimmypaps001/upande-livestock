# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A vet is a record, not a name typed into a case.

Livestock Health Case carried "Vet Called" (a tick) and "Vet Name" (free text);
Livestock Disposal carried "Seen By" (`custom_vet_by`, a User). Both are replaced
by a `vet` link to Livestock Vet.

Existing values are carried across, never lost:

* a case's vet name that matches a Livestock Vet by name (case-insensitively)
  becomes that case's `vet`; any other name is written into the case's outcome
  notes as "[migrated] Vet: <name>". A case ticked "Vet Called" with no name
  says "[migrated] Vet: called (not named)".
* a disposal's `custom_vet_by` user becomes the vet whose user (or whose
  Employee's user) it is; with no such vet it is written into the disposal's
  reason details as "[migrated] Vet seen by: <user>".

Then the old columns go. Runs after model sync, which adds `vet` and the new
doctype but leaves the old columns until this drops them. A site with no vets
yet (every live site, on first deploy) therefore keeps its history as notes.
"""

import frappe

from upande_livestock.patches._fold import (
	MARKER, append_lines, column_exists, drop_column,
)

CASE = "Livestock Health Case"
DISPOSAL = "Livestock Disposal"


def _vets_by_name():
	return {
		(v.vet_name or "").strip().lower(): v.name
		for v in frappe.get_all("Livestock Vet", fields=["name", "vet_name"])
		if (v.vet_name or "").strip()
	}


def _vet_for_user(user):
	name = frappe.db.get_value("Livestock Vet", {"user": user}, "name")
	if name:
		return name
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	return frappe.db.get_value("Livestock Vet", {"employee": employee}, "name") if employee else None


def fold_cases():
	if not (column_exists(CASE, "vet_name") or column_exists(CASE, "vet_called")):
		return
	vets = _vets_by_name()
	named = "vet_name" if column_exists(CASE, "vet_name") else "NULL"
	called = "vet_called" if column_exists(CASE, "vet_called") else "0"
	for row in frappe.db.sql(
		f"""SELECT name, vet, outcome_notes, {named} AS vet_name, {called} AS vet_called
		    FROM `tab{CASE}` WHERE IFNULL({named}, '') != '' OR IFNULL({called}, 0) = 1""",
		as_dict=True,
	):
		typed = (row.vet_name or "").strip()
		match = vets.get(typed.lower()) if typed else None
		if match and not row.vet:
			frappe.db.set_value(CASE, row.name, "vet", match, update_modified=False)
		elif not match:
			line = f"{MARKER} Vet: {typed or 'called (not named)'}"
			append_lines(CASE, row.name, "outcome_notes", row.outcome_notes, [line])


def fold_disposals():
	if not column_exists(DISPOSAL, "custom_vet_by"):
		return
	for row in frappe.db.sql(
		f"""SELECT name, vet, reason_details, custom_vet_by FROM `tab{DISPOSAL}`
		    WHERE IFNULL(custom_vet_by, '') != ''""",
		as_dict=True,
	):
		match = _vet_for_user(row.custom_vet_by)
		if match and not row.vet:
			frappe.db.set_value(DISPOSAL, row.name, "vet", match, update_modified=False)
		elif not match:
			line = f"{MARKER} Vet seen by: {row.custom_vet_by}"
			append_lines(DISPOSAL, row.name, "reason_details", row.reason_details, [line])


def execute():
	fold_cases()
	fold_disposals()
	for doctype, fields in ((CASE, ("vet_called", "vet_name")), (DISPOSAL, ("custom_vet_by",))):
		frappe.db.delete("Property Setter", {"doc_type": doctype, "field_name": ("in", fields)})
		# A Custom Field of the same name would keep the column alive.
		frappe.db.delete("Custom Field", {"dt": doctype, "fieldname": ("in", fields)})
		frappe.clear_cache(doctype=doctype)
		for column in fields:
			drop_column(doctype, column)
