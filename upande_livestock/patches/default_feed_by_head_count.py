# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Feed by Head Count is on wherever it was never set.

On is how every farm on this app has always fed: head count times the ration
per head. Mutara turns it off to type the group's total instead. The patch
only writes where nothing is stored, so a farm that already chose keeps its
choice, and a site that never runs it still reads as on (`_head_count`).
"""

import frappe

from upande_livestock.serverscripts.common.timings import read_setting


def execute():
	if read_setting("feed_by_head_count") in (None, ""):
		frappe.db.set_single_value("Livestock Settings", "feed_by_head_count", 1)
	frappe.clear_cache(doctype="Livestock Settings")
