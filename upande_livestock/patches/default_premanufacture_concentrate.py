# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Pre-manufacture Concentrate is on wherever it was never set.

On is today's two-stage flow, so nothing changes on any site until a manager
turns the switch off. The patch only writes where there is no stored value, so
a farm that already chose is left alone.
"""

import frappe

from upande_livestock.serverscripts.common.timings import read_setting


def execute():
	if read_setting("premanufacture_concentrate") in (None, ""):
		frappe.db.set_single_value("Livestock Settings", "premanufacture_concentrate", 1)
	frappe.clear_cache(doctype="Livestock Settings")
