# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Rename the Animal* doctype family to Livestock*.

Runs in [pre_model_sync] — BEFORE doctype JSON is synced. If it ran after, the
sync would create empty `tabLivestock Event` tables from the new JSON and orphan
the populated `tabAnimal Event`.

Longest old name first, so "Animal Diagnosis System Check" is not partially
matched by a "Animal Diagnosis" rename.

DocType.before_rename() calls check_developer_mode(), which raises unless
developer_mode is on, the doctype is Custom, or frappe.flags.in_patch is set.
The Frappe patch runner normally sets that flag for the duration of
`bench migrate`. This site cannot run `bench migrate` (broken by an unrelated
lending patch), so this patch is invoked directly via `bench execute` instead,
which does not set the flag. We set it ourselves for the duration of the
rename and restore the previous value afterwards.
"""

import frappe
from frappe.model.rename_doc import rename_doc

RENAMES = [
	("Animal Diagnosis System Check", "Livestock Diagnosis System Check"),
	("Animal Health Treatment", "Livestock Health Treatment"),
	("Animal Weight Record", "Livestock Weight Record"),
	("Animal Health Case", "Livestock Health Case"),
	("Animal Drug Issue", "Livestock Drug Issue"),
	("Animal Diagnosis", "Livestock Diagnosis"),
	("Animal Disposal", "Livestock Disposal"),
	("Animal Disease", "Livestock Disease"),
	("Animal Event", "Livestock Event"),
]


def execute():
	previous_in_patch = frappe.flags.get("in_patch")
	frappe.flags.in_patch = True
	try:
		for old, new in RENAMES:
			if not frappe.db.exists("DocType", old):
				continue
			if frappe.db.exists("DocType", new):
				frappe.log_error(
					message=f"Both {old} and {new} exist; skipping rename.",
					title="Livestock rename conflict",
				)
				continue
			rename_doc(doctype="DocType", old=old, new=new, force=True, ignore_permissions=True)
	finally:
		frappe.flags.in_patch = previous_in_patch

	frappe.clear_cache()
