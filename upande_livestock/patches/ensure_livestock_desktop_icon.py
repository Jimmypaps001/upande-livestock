# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Livestock desk tile shows the vector livestock_logo.svg and no PNG.

The tile shows ``logo_url`` (else ``icon_image``) through ``<img>``. On a site where the
Livestock Desktop Icon still carries one of this app's own images (upande_logo.png, upande_mark.png,
or livestock_logo.svg as a raster ``icon_image``), a PNG scaled by the browser goes soft at desk
zoom and on HiDPI screens, and the animated SVG never shows. So:

* ``logo_url`` is set to the SVG when it is empty or one of this app's own images;
* ``icon_image`` is cleared when it is empty or one of this app's own images.

Anything else (a logo someone uploaded, another app's image) is left alone, as are the icon's
link, type and roles. Only the Desktop Icon named "Livestock" is touched. Skipped on a site
without the Desktop Icon doctype or its columns. Idempotent.
"""

import frappe

LOGO = "/assets/upande_livestock/images/livestock_logo.svg"
OWN = "/assets/upande_livestock/images/"


def _ours(value) -> bool:
	return not value or str(value).startswith(OWN)


def execute():
	if not frappe.db.table_exists("Desktop Icon"):
		return
	if not frappe.db.exists("Desktop Icon", "Livestock"):
		return
	values = {}
	if frappe.db.has_column("Desktop Icon", "logo_url"):
		logo = frappe.db.get_value("Desktop Icon", "Livestock", "logo_url")
		if _ours(logo) and logo != LOGO:
			values["logo_url"] = LOGO
	if frappe.db.has_column("Desktop Icon", "icon_image"):
		image = frappe.db.get_value("Desktop Icon", "Livestock", "icon_image")
		if image and _ours(image):
			values["icon_image"] = None
	if not values:
		return
	frappe.db.set_value("Desktop Icon", "Livestock", values, update_modified=False)
	frappe.cache.delete_value("desktop_icons")
	frappe.clear_cache()
