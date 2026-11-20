# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Create Livestock Sire records from the free-text sires and link the records.

The same routine as the manager's `match_sires` tool, run for real. Never
rewrites the typed text; reuses a sire that already exists, so it is safe to run
again.
"""

import frappe


def execute():
	frappe.reload_doc("upande_livestock", "doctype", "livestock_sire")
	frappe.reload_doc("upande_livestock", "doctype", "livestock_event")
	frappe.reload_doc("upande_livestock", "doctype", "animal")
	from upande_livestock.serverscripts.common.livestock_sire import match_all

	match_all(dry_run=False)
