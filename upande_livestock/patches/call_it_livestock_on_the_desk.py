# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Drop the "Upande" from what the desk calls this app, and a dead link with it.

The farm is already inside Upande's ERP by the time it sees a sidebar, so the
prefix says nothing and costs the width of a word on every screen. The desk
calls it Livestock.

ONLY THE DISPLAY TEXT MOVES. The package is still `upande_livestock`, the
Workspace is still NAMED "Upande Livestock", the module is still "Upande
Livestock", and the route is still /app/upande-livestock — because those are
what other things point AT. Every doctype in the app is owned by that module,
the sidebar's Home item links to the workspace by name, and the quick-link tiles
carry the route. Renaming them would break all three to change a word on screen.
The React app keeps its own headings; this is the desk.

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
	# The tile on the desk home. Keyed by `label`, which is also the text.
	# `link_to` is left alone: it points at the Workspace Sidebar by NAME.
	for name in frappe.get_all(
		"Desktop Icon", filters={"label": OLD}, pluck="name"
	):
		frappe.db.set_value("Desktop Icon", name, "label", NEW, update_modified=False)

	# The sidebar header. Renaming `title` through the ORM would re-export the
	# fixture under a new filename and leave the old one behind, so the column is
	# written directly and the file is renamed in the repo alongside this patch.
	if frappe.db.exists("Workspace Sidebar", OLD):
		frappe.db.set_value("Workspace Sidebar", OLD, "title", NEW, update_modified=False)

	# The workspace itself ships its title, but a site that migrated before this
	# has the old value cached in a row the fixture will not overwrite if it has
	# been touched on the desk.
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
