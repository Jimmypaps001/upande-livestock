# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The units each feed may be written in, and what one of each weighs.

For the unit picker on every recipe and feeding line: the item's stock unit
and every row of its UOM Conversion Detail, each with its kilos per unit, so
the page can show "3 Litre ≈ 4.2 kg" and run its nutrition and percentages on
kilos. See `_units`. Reads Item, so it is read-guarded on Item.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding._units import item_units


@frappe.whitelist()
def feed_units(items=None):
	"""{ok, units: {item_code: {stock_uom, uoms: [{uom, factor, kg}]}}}."""

	def go():
		guard_read("Item")
		codes = frappe.parse_json(items) if isinstance(items, str) else (items or [])
		if not isinstance(codes, list):
			codes = [codes]
		return {"ok": True, "units": item_units([str(c) for c in codes][:500])}

	return run(go, "livestock feed_units failed")
