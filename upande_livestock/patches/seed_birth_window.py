# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Seed the birth window and the retro-diagnosis switch wherever they are unset.

A birth is recorded straight away only when the dam's service puts it between
service + 270 and service + 295 days (or a pregnancy diagnosis confirmed her).
The farm agreed those numbers for its cattle; a Single field with no row reads
back as 0 and a window of 0..0 would refuse every birth, so the defaults are
written rather than left to the DocType. The switch that lets a back-recorded
service carry a pregnancy diagnosis starts on.

Only writes where nothing is stored, so a farm that already chose keeps it.
"""

import frappe

from upande_livestock.serverscripts.common.timings import read_setting

DEFAULTS = {
	"gestation_window_min_days": 270,
	"gestation_window_max_days": 295,
	"allow_retro_pregnancy_diagnosis": 1,
}


def execute():
	frappe.reload_doc("upande_livestock", "doctype", "livestock_settings")
	for field, value in DEFAULTS.items():
		if read_setting(field) in (None, ""):
			frappe.db.set_single_value("Livestock Settings", field, value)
	frappe.clear_cache(doctype="Livestock Settings")
