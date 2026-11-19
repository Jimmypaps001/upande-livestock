# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Feed types: System and Day sheet on, Manual configuration off, on desk and phone.

Writes only where nothing is stored, so a farm that already chose keeps its
choice. The Manual configuration tab stays hidden until somebody turns it on.
"""

import frappe

from upande_livestock.serverscripts.common.timings import read_setting
from upande_livestock.serverscripts.feeding import _feed_types as FT


def execute():
	for mode in FT.MODES:
		for where in ("desk", "phone"):
			name = FT.field(mode, where)
			if read_setting(name) in (None, ""):
				on = FT.MODES[mode][1 if where == "desk" else 2]
				frappe.db.set_single_value("Livestock Settings", name, on)
	frappe.clear_cache(doctype="Livestock Settings")
