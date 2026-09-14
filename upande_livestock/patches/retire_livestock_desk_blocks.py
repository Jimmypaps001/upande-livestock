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

The desk surfaces go with them. Everything those blocks did is a React screen
now, and the workspace is a grid of links to those screens — which is the whole
point of having built them.

`Livestock Rations` is dropped outright: this app is the only thing that ever
shipped it.

`Livestock Dashboard` and `Livestock Operations` are NOT dropped, and not out
of caution. **upande_scp/fixtures/custom_html_block.json ships its own copies of
both** — older ones, and different: its Operations block is 17 KB of script
against this app's 106 KB. So the two apps have been overwriting each other's
livestock blocks on every migrate, whichever ran last. Deleting them here would
be a patch fighting another app's fixture and losing on the next `bench
migrate`. They ship from this app no longer and no workspace points at them, so
they are unreachable either way; taking them off the site is a change to
upande_scp, and the farm's call.
"""

import frappe

RETIRED_WORKSPACES = ("Livestock Operations", "Livestock Rations")
RETIRED_BLOCKS = ("Livestock Rations",)


def execute():
	if frappe.db.table_exists("Workspace"):
		for name in RETIRED_WORKSPACES:
			if frappe.db.exists("Workspace", name):
				frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)
	if frappe.db.table_exists("Custom HTML Block"):
		for name in RETIRED_BLOCKS:
			if frappe.db.exists("Custom HTML Block", name):
				frappe.delete_doc(
					"Custom HTML Block", name, force=True, ignore_permissions=True)
	frappe.db.commit()
