# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Permanent fix for the v16 desk grid hiding newly-added app icons.

The desk grid (frappe/desk/page/desktop) renders from a per-user ``Desktop
Layout`` snapshot. A layout saved before this app's ``Desktop Icon`` existed
omits it, so the card never appears — even though the icon is correctly in the
user's permission-filtered ``frappe.boot.desktop_icons``.

On login we drop the user's Desktop Layout **iff** it is missing a desktop icon
the user is actually permitted to see (from the same permission-filtered boot
list). The grid then rebuilds natively from the boot, including the new icon.
Deleting only when something permitted is missing keeps a user's custom
arrangement in place the rest of the time.
"""

import frappe


def clear_stale_desktop_layout(login_manager=None):
	try:
		user = frappe.session.user
		if not user or user == "Guest":
			return
		if not frappe.db.exists("Desktop Layout", user):
			return

		layout = frappe.db.get_value("Desktop Layout", user, "layout") or ""

		# Labels the user is permitted to see on the grid, from the same
		# permission-filtered source the boot uses.
		from frappe.desk.doctype.desktop_icon.desktop_icon import get_desktop_icons

		bootinfo = frappe._dict({"workspace_sidebar_item": _sidebar_map()})
		permitted = get_desktop_icons(user=user, bootinfo=bootinfo)
		missing = [
			i for i in permitted if not i.get("parent_icon") and i.get("label") and i["label"] not in layout
		]

		if missing:
			frappe.delete_doc("Desktop Layout", user, force=True, ignore_permissions=True)
			frappe.cache.hdel("desktop_icons", user)
	except Exception:
		frappe.log_error(title="upande_livestock: clear_stale_desktop_layout failed")


def _sidebar_map() -> dict:
	from frappe.boot import get_sidebar_items
	from frappe.desk.desktop import get_workspaces

	allowed = [p.get("name") for p in (get_workspaces().get("pages") or [])]
	return get_sidebar_items(allowed)
