# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Every herd's standing ration, and the feeds a new line could name.

The read half of `set_herd_ration`. One call rather than one per herd, because
the editor's first question is "which herd" and a screen that fetched a ration
only after the answer would blank and refill on every click.

LINES ARE IN THE UNITS THE RECIPE IS WRITTEN IN. Hay is 1.5 kg on a lactating
ration and stocked in BALE at 0.07 — handing an operator "0.105 BALE" where the
recipe says "1.5 Kilogram" is not the same fact in another unit, it is a
fourteenth of the hay in a number they cannot check against the mixer. See
`_recipe_lines`, which this reuses rather than re-deriving.

What a ration may be built from is every feed item the farm already buys or
mixes — read off the BOMs that exist rather than off an item group, because a
group is a filing decision and a recipe is evidence. An item nobody has ever
put in a ration is not offered: naming a new feed product is the farm's call,
and a picker that offered the whole item master would invite a ration made of
fence posts.

Read-guarded on BOM: it discloses what the farm feeds.
"""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding._recipe_lines import lines_for


@frappe.whitelist()
def herd_rations(payload=None):
	"""Every herd, its ration, and what a line may name."""

	def go():
		guard_read("BOM")
		herds = frappe.get_all(
			"Herds", fields=["name", "bom", "number_of_animals"], order_by="name asc")
		lines = lines_for([h.bom for h in herds if h.bom])
		boms = {
			b.name: b
			for b in frappe.get_all(
				"BOM", filters={"name": ["in", [h.bom for h in herds if h.bom] or [""]]},
				fields=["name", "item", "item_name", "quantity", "uom"])
		}

		rows = []
		for h in herds:
			bom = boms.get(h.bom or "")
			ration = lines.get(h.bom or "", [])
			per_head = flt(bom.quantity) if bom else 0.0
			heads = flt(h.number_of_animals)
			rows.append({
				"herd": h.name,
				"heads": heads,
				"bom": h.bom,
				"ration_item": bom.item if bom else None,
				"ration_name": (bom.item_name or bom.item) if bom else None,
				"per_head_kg": per_head,
				"day_kg": per_head * heads,
				"lines": ration,
				# The invariant `set_herd_ration` enforces on anything it writes,
				# reported for what is already there: six of the live site's
				# rations state an output their own lines do not add up to, so
				# they issue less feed than they consume. Said on the screen
				# rather than left for somebody to notice.
				"lines_total": round(sum(flt(r["qty"]) for r in ration), 3),
				"balanced": abs(sum(flt(r["qty"]) for r in ration) - per_head) < 0.0005,
			})

		return {"ok": True, "herds": rows, "feeds": _feeds()}

	return run(go, "livestock herd_rations failed")


def _feeds():
	"""Items that appear in a recipe on this farm, with what is in store."""
	codes = frappe.db.sql_list(
		"""SELECT DISTINCT bi.item_code FROM `tabBOM Item` bi
		   JOIN `tabBOM` b ON b.name = bi.parent
		   WHERE b.docstatus = 1"""
	)
	if not codes:
		return []
	rows = frappe.get_all(
		"Item", filters={"name": ["in", codes]},
		fields=["name as item_code", "item_name", "stock_uom"], order_by="item_name asc")
	on_hand = dict(frappe.db.sql(
		"""SELECT item_code, IFNULL(SUM(actual_qty), 0) FROM `tabBin`
		   WHERE item_code IN %(codes)s GROUP BY item_code""", {"codes": tuple(codes)}))
	return [
		{
			"value": r.item_code,
			"label": r.item_name or r.item_code,
			"uom": r.stock_uom,
			"on_hand": flt(on_hand.get(r.item_code)),
		}
		for r in rows
	]
