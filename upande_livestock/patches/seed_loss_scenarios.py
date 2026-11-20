# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Seed the example loss scenarios and default "Sale of an insured animal waits for".

Written only where nothing is stored, so a farm's own choice is kept.
"""

import frappe

from upande_livestock.serverscripts.common.loss import DEFAULT_GATE, ensure_loss_scenarios
from upande_livestock.serverscripts.common.timings import read_setting


def execute():
	frappe.reload_doc("upande_livestock", "doctype", "livestock_loss_document")
	frappe.reload_doc("upande_livestock", "doctype", "livestock_loss_scenario")
	frappe.reload_doc("upande_livestock", "doctype", "livestock_loss")
	if read_setting("sale_waits_for") in (None, ""):
		frappe.db.set_single_value("Livestock Settings", "sale_waits_for", DEFAULT_GATE)
	ensure_loss_scenarios()
	frappe.clear_cache(doctype="Livestock Settings")
