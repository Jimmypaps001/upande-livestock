# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Shoats home: every By-number herd with head by class, live weight, withdrawal and breeding; totals roll up
to Sheep, Goats and Shoats."""

import frappe
from frappe.utils import today

from upande_livestock.serverscripts.common import shoats
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def shoat_herds(species=None):
	def go():
		guard_read("Herds")
		rows = [shoats.herd_row(n) for n in shoats.shoat_herd_names()]
		if species:
			rows = [r for r in rows if r["species"] == species]
		return {"ok": True, "today": today(), "herds": rows, "totals": shoats.totals(rows), "warnings": []}

	return run(go, "livestock shoat_herds failed")
