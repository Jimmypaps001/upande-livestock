# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Bull purpose: Kaitet sells bulls as soon as they are born.

Written only where nothing is stored, so a farm that already chose (Mutara, on
fattening) keeps its choice.
"""

import frappe

from upande_livestock.serverscripts.common.timings import read_setting


def execute():
	if read_setting("bull_purpose") in (None, ""):
		frappe.db.set_single_value("Livestock Settings", "bull_purpose", "Cull for sale at birth")
	frappe.clear_cache(doctype="Livestock Settings")
