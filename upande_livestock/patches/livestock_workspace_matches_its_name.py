# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Move the workspace's NAME to meet the title the desk already shows.

`call_it_livestock_on_the_desk` set the Workspace's title to "Livestock" and
deliberately left its name as "Upande Livestock", on the reasoning that the name
is what other things point at. That reasoning held for the module — which is a
separate record and keeps its name — but not for the workspace, and the split it
left behind is what made the desk card 404.

Frappe does not treat a Workspace's name and title as two independent fields.
The doctype autonames `field:label`, and `Workspace.before_export` collapses
them the moment they drift:

    if doc.title != doc.label and doc.label == doc.name:
        self.name = doc.name = doc.label = doc.title

THE DESK READS BOTH, THROUGH DIFFERENT FIELDS. The card on the desk grid builds
its href from the workspace's TITLE (frappe/desk/page/desktop/desktop.js):

    let workspaces = frappe.workspaces[frappe.router.slug(first_link.link_to)];
    route = frappe.utils.generate_route({type: "workspace", name: workspaces.title, ...})

while the router resolves a route back to a workspace out of a map keyed by the
slug of its NAME (frappe/public/js/frappe/desk.js, setup_workspaces):

    frappe.workspaces[frappe.router.slug(page.name)] = page;

Title "Livestock" and name "Upande Livestock" therefore aimed the card at
/desk/livestock, which no workspace answered to. The router fell through to a
desk Page, `frappe.desk.desk_page.getpage("livestock")` raised, and the farm got
"Page livestock not found" behind a bare "Not found" dialog.

The sidebar and the app switcher survived only because they take a different
function — `frappe.utils.get_route_for_icon` slugs `link_to`, i.e. the name —
which is why the app looked fine from everywhere except the one card people
actually click.

So the name moves. The route becomes /app/livestock, and everything that points
AT the workspace moves with it: the sidebar's Home item and the Desktop Icon here,
the apps-screen hook, the desk-grid injector and the frontend stub in the source.

Runs PRE model sync: `sync_all` imports workspace/livestock/livestock.json, and a
rename that happened after that import would be renaming onto a workspace the
import had just created alongside the old one.
"""

import frappe

OLD = "Upande Livestock"
NEW = "Livestock"


def execute():
	rename_workspace()
	repoint_workspace_references()
	rename_desktop_icon()
	frappe.clear_cache()


def rename_workspace():
	if not frappe.db.exists("Workspace", OLD):
		return

	if frappe.db.exists("Workspace", NEW):
		# The renamed fixture already landed on this site, so the old row is a
		# leftover rather than the thing to rename. Safe to drop: `on_trash` only
		# takes the sidebar and the desktop icon down with it for a workspace with
		# no module, and this one has one.
		frappe.delete_doc("Workspace", OLD, force=True, ignore_permissions=True)
		return

	frappe.rename_doc("Workspace", OLD, NEW, force=True)
	# `label` is the autoname source and `title` is what the desk card slugs.
	# Renaming moves neither on its own, and leaving either behind rebuilds the
	# exact split this patch exists to close.
	frappe.db.set_value("Workspace", NEW, {"label": NEW, "title": NEW}, update_modified=False)


def repoint_workspace_references():
	# rename_doc updates dynamic links itself, but not the delete branch above,
	# and a row left pointing at the old name is a sidebar entry that opens nothing.
	for name in frappe.get_all(
		"Workspace Sidebar Item",
		filters={"link_type": "Workspace", "link_to": OLD},
		pluck="name",
	):
		frappe.db.set_value("Workspace Sidebar Item", name, "link_to", NEW, update_modified=False)

	for user in frappe.get_all("User", filters={"default_workspace": OLD}, pluck="name"):
		frappe.db.set_value("User", user, "default_workspace", NEW, update_modified=False)

	for child in frappe.get_all("Workspace", filters={"parent_page": OLD}, pluck="name"):
		frappe.db.set_value("Workspace", child, "parent_page", NEW, update_modified=False)


def rename_desktop_icon():
	# Desktop Icon autonames `field:label` as well, and the earlier patch moved the
	# label without the name — so the card is labelled "Livestock" in a row still
	# named "Upande Livestock". The fixture ships name "Livestock": leave the row
	# where it is and the next sync_fixtures INSERTS a second card beside it.
	if not frappe.db.exists("Desktop Icon", OLD):
		return

	if frappe.db.exists("Desktop Icon", NEW):
		frappe.delete_doc("Desktop Icon", OLD, force=True, ignore_permissions=True)
		return

	frappe.rename_doc("Desktop Icon", OLD, NEW, force=True)
	frappe.db.set_value("Desktop Icon", NEW, "label", NEW, update_modified=False)
