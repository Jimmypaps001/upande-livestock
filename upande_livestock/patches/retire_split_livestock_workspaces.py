# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Fold three livestock workspaces back into one.

The desk grew a workspace per surface — Upande Livestock, Livestock Operations,
Livestock Rations — which was three sidebar entries for one app, and the moment
the React screens were finished it was three entries for a UI that now lives
somewhere else entirely. One workspace carries the dashboard, the desk ration
editor, and a quick link to each of the thirty-one app screens.

Deleting the fixture file is not enough: Frappe creates a Workspace on migrate
and never removes one it has stopped shipping, so a site that migrated before
this keeps both of the old entries forever. Hence a patch.

THE BLOCKS THEMSELVES ARE LEFT ALONE. `Livestock Operations` is 106 KB of
working desk UI, and a patch that ran once and dropped it would take a surface
the farm may still want with no way back. The workspace that pointed at it is
gone, so it no longer appears in the sidebar; restoring it is a workspace, not a
rewrite.
"""

import frappe

RETIRED = ("Livestock Operations", "Livestock Rations")


def execute():
	if not frappe.db.table_exists("Workspace"):
		return
	for name in RETIRED:
		if frappe.db.exists("Workspace", name):
			frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)
	frappe.db.commit()
