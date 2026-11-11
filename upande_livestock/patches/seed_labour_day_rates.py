# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The labour day rates start at what the farm pays today.

Mutara's tracker ("Labour Cost" sheet, 2026) pays every worker KES 400 a day,
feedlot hands and herders alike. The rates live in Livestock Settings, not in
code, so a pay rise is a settings change; this patch only gives the fields the
value they have today so the first day's labour is costed without anyone
having to find the setting first.

Writes only where nothing is stored, so a farm that has already set its rates
(or deliberately cleared one) keeps them.
"""

import frappe

from upande_livestock.serverscripts.common.timings import read_setting

#: KES per worker per day, from the farm's own sheet on 2026-11-11.
SHEET_DAY_RATE = 400

FIELDS = ("labour_rate_feedlot_workers", "labour_rate_herders", "labour_rate_other")


def execute():
	meta = frappe.get_meta("Livestock Settings")
	for field in FIELDS:
		if not meta.has_field(field):
			continue
		if read_setting(field) in (None, ""):
			frappe.db.set_single_value("Livestock Settings", field, SHEET_DAY_RATE)
	frappe.clear_cache(doctype="Livestock Settings")
