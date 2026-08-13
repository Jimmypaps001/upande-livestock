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

The same flag also makes DocType.after_rename() skip
rename_files_and_folders() — exactly what we want here, since Step 1 of this
rename already used `git mv` to move each doctype's directory and files on
disk before this patch ever runs.
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
	"""Rename each (old, new) pair in RENAMES, honoring the in_patch developer-mode bypass.

	If old is missing, the pair is treated as already renamed and skipped —
	this keeps re-runs after a transient failure safe. If both old and new
	exist, that is an unrecoverable conflict: skipping it here would let the
	patch report success while one rename silently never happened (leaving
	rows stranded in the old table), so we throw instead and require manual
	resolution before the patch can be re-run.
	"""
	previous_in_patch = frappe.flags.get("in_patch")
	frappe.flags.in_patch = True
	try:
		for old, new in RENAMES:
			if not frappe.db.exists("DocType", old):
				continue
			if frappe.db.exists("DocType", new):
				frappe.throw(
					f"Both '{old}' and '{new}' DocType records exist. This rename cannot "
					"proceed automatically — resolve the conflict manually (merge or "
					"delete one of them) before re-running this patch.",
					title="Livestock rename conflict",
				)
			rename_doc(doctype="DocType", old=old, new=new, force=True, ignore_permissions=True)
	finally:
		frappe.flags.in_patch = previous_in_patch

	frappe.clear_cache()
