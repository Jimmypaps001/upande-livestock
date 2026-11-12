# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Livestock apps-screen tile, as Production's: the vector livestock_logo.svg, no PNG anywhere.

The tile shows ``logo_url`` (else ``icon_image``) through ``<img>``; both are pointed at the SVG,
or cleared, so a stale upande_logo.png on a site (scaled up by the browser, soft at desk zoom and
on HiDPI screens) never comes back. It stays a same-tab Workspace Sidebar link: Frappe's
desktop.js builds a relative /desk/livestock?sidebar=Livestock route for it (an External icon
would open a new tab), and a Link icon is shown only to users who can see the Livestock sidebar
(an App icon would be shown to everyone, since this app declares no has_permission). Idempotent.
"""

import frappe

LOGO = "/assets/upande_livestock/images/livestock_logo.svg"


def execute():
	if not frappe.db.exists("Desktop Icon", "Livestock"):
		return
	frappe.db.set_value("Desktop Icon", "Livestock", {
		"logo_url": LOGO,
		"icon_image": None,
		"link_type": "Workspace Sidebar",
		"link_to": "Livestock",
		"link": None,
	}, update_modified=False)
	frappe.cache.delete_value("desktop_icons")
	frappe.clear_cache()
