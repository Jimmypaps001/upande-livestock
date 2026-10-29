# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Breeding by numbers: every mating with expected lambing / kidding, status and what was born."""

import frappe
from frappe.utils import today

from upande_livestock.serverscripts.common import shoats
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def shoat_breeding(herd=None):
	def go():
		guard_read("Herd Count Event")
		rows = shoats.matings(herd or None)
		return {"ok": True, "today": today(), "gestation_days": shoats.gestation_days(), "matings": rows,
		        "due": [m for m in rows if m["status"] in ("Due", "Overdue")], "warnings": []}

	return run(go, "livestock shoat_breeding failed")
