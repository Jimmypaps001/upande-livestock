# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Seed the Calf asset settings, only where they are still unset.

Item "herd", category "Herd" and location "Kapkolia" are the farm's own herd
asset pattern; each is set only when it exists on the site, so a site without
them keeps a blank and the birth path says so instead of failing. Never
overwrites a value a person has chosen. Safe to run again.
"""

import frappe


def execute():
	frappe.reload_doc("upande_livestock", "doctype", "livestock_settings")
	wanted = (
		("calf_asset_item", "Item", "herd"),
		("calf_asset_category", "Asset Category", "Herd"),
		("calf_asset_location", "Location", "Kapkolia"),
	)
	for field, doctype, value in wanted:
		if not frappe.db.get_single_value("Livestock Settings", field) and frappe.db.exists(doctype, value):
			frappe.db.set_single_value("Livestock Settings", field, value)
	if not frappe.db.get_single_value("Livestock Settings", "calf_asset_value"):
		frappe.db.set_single_value("Livestock Settings", "calf_asset_value", 5000)
	if not frappe.db.get_single_value("Livestock Settings", "calf_asset_naming_series"):
		frappe.db.set_single_value("Livestock Settings", "calf_asset_naming_series", "ACC-ASS-.YYYY.-")
	# create_calf_asset defaults to on; an untouched site has no stored value yet.
	# A Check that was never stored reads back as 0, so look for the stored row.
	if not frappe.db.exists(
		"Singles", {"doctype": "Livestock Settings", "field": "create_calf_asset"}
	):
		frappe.db.set_single_value("Livestock Settings", "create_calf_asset", 1)
