# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Drop the "Upande" from what the desk calls this app, and a dead link with it.

The farm is already inside Upande's ERP by the time it sees a sidebar, so the
prefix says nothing and costs the width of a word on every screen. The desk
calls it Livestock.

ONLY THE DISPLAY TEXT MOVES. The package is still `upande_livestock` and the
module is still "Upande Livestock" — every doctype in the app is owned by that
module. The React app keeps its own headings; this is the desk.

CORRECTION, see `livestock_workspace_matches_its_name`: this patch also left the
Workspace NAMED "Upande Livestock" while setting its title to "Livestock", on the
same reasoning. That one does not hold — Frappe autonames a Workspace from its
label and the desk grid slugs the card's href from the TITLE while the router
resolves routes by NAME, so the split aimed the card at a route nothing answered
to. The workspace has since been renamed to "Livestock"; the stanza below is a
no-op on any site that gets both patches.

TWO OF THE THREE ARE SITE RECORDS, which is why a fixture edit is not enough.
The Workspace title ships in the fixture and arrives with migrate. But the
Workspace Sidebar exports itself FROM the desk rather than importing, and the
Desktop Icon is created on the site by Frappe and never shipped at all — so both
keep the old text on every site that has already migrated, forever, unless
something goes and changes them.
"""

import frappe

OLD = "Upande Livestock"
NEW = "Livestock"


def execute():
	# The tile on the desk home. Both fields move together: `label` is the text
	# AND the key the sidebar is looked up by, and `link_to` is what it opens.
	# Moving one without the other is what made the icon disappear.
	for name in frappe.get_all(
		"Desktop Icon",
		filters={"link_type": "Workspace Sidebar", "link_to": OLD},
		pluck="name",
	):
		frappe.db.set_value(
			"Desktop Icon", name, {"label": NEW, "link_to": NEW}, update_modified=False
		)

	# The sidebar has to be RENAMED, not merely re-titled, and that is the whole
	# trap. The desk decides whether to draw an icon at all by looking its
	# sidebar up in the boot map:
	#
	#     sidebar = bootinfo.workspace_sidebar_item.get(icon.label.lower())
	#     permitted = bool(sidebar and sidebar["items"])
	#
	# and that map is keyed by the sidebar's NAME, not its title
	# (frappe/boot.py: get_sidebar_items). Change the icon's label to "Livestock"
	# while the sidebar is still named "Upande Livestock" and the lookup misses,
	# `permitted` is False, and the app VANISHES from the desk entirely — which
	# is exactly what happened before this line existed.
	if frappe.db.exists("Workspace Sidebar", OLD):
		frappe.rename_doc("Workspace Sidebar", OLD, NEW, force=True)
	if frappe.db.exists("Workspace Sidebar", NEW):
		frappe.db.set_value("Workspace Sidebar", NEW, "title", NEW, update_modified=False)

	# The workspace itself ships its title, but a site that migrated before this
	# has the old value cached in a row the fixture will not overwrite if it has
	# been touched on the desk. Superseded by livestock_workspace_matches_its_name,
	# which renames the row outright — kept only for a site that ran this patch
	# before that one existed.
	if frappe.db.exists("Workspace", OLD):
		frappe.db.set_value("Workspace", OLD, "title", NEW, update_modified=False)

	# And the sidebar's dead Operations link. `retire_livestock_desk_blocks`
	# folded three workspaces into one and deleted Livestock Operations, but the
	# sidebar item pointing AT it was left behind — a row in a child table the
	# workspace patch never looked at. It has been a link to nothing ever since.
	for name in frappe.get_all(
		"Workspace Sidebar Item",
		filters={"link_type": "Workspace", "link_to": "Livestock Operations"},
		pluck="name",
	):
		frappe.db.delete("Workspace Sidebar Item", name)

	frappe.clear_cache()
