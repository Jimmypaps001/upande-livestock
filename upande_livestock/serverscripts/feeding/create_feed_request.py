# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One Material Request for everything the feed store needs."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.feeding.feed_procurement import _feed_store


@frappe.whitelist()
def create_feed_request(payload):
	"""Raise ONE draft Material Request for the lines the operator kept.

	ONE REQUEST, NOT ONE PER ITEM. The farm buys feed from a handful of
	suppliers on one trip, and six separate requests for the same trip is six
	things to chase and six chances for one to be missed. Consolidating is the
	whole point of the screen.

	LEFT IN DRAFT, DELIBERATELY. Submitting a Material Request is the farm
	saying it intends to buy; that is a person's decision and it belongs to
	whoever talks to the supplier. This gets the arithmetic and the typing out
	of their way and stops there.

	The quantities come from the CALLER, not recomputed here. The screen shows
	what the projection suggests and lets somebody change it — a store keeper
	who knows a supplier sells in half-tonne lots, or that the maize is coming
	off the farm's own fields next week, is right and the arithmetic is not.
	"""

	def go():
		guard("Material Request")
		d = as_dict(payload)
		rows = _clean(d.get("items"))
		if not rows:
			frappe.throw(_("Nothing to order. Pick at least one feed."))

		warehouse = (d.get("warehouse") or "").strip() or _feed_store()
		if not warehouse:
			frappe.throw(
				_("There is no feed store set, so there is nowhere for this to be "
				  "delivered. Set one on Livestock Settings.")
			)

		# A date the feed is actually wanted, not today: ERPNext requires a
		# schedule date per line and defaults it to today, which reads as "this
		# was needed before it was ordered" on every row.
		wanted = d.get("schedule_date") or add_days(today(), 7)

		doc = frappe.new_doc("Material Request")
		doc.material_request_type = "Purchase"
		doc.transaction_date = today()
		doc.schedule_date = wanted
		doc.company = frappe.db.get_single_value(
			"Livestock Settings", "custom_default_company") or doc.company
		# SCP's mandatory fields on Material Request, on the parent and on every
		# line. `custom_farm` is taken from the store the feed is delivered
		# into, so it follows the site rather than being hardcoded — the same
		# rule build_feed_rations uses for a BOM's farm.
		farm = frappe.db.get_value("Warehouse", warehouse, "custom_farm")
		if doc.meta.has_field("custom_farm"):
			if not farm:
				frappe.throw(
					_("{0} is not linked to a Farm, and a Material Request needs one. "
					  "Set the farm on the warehouse.").format(warehouse)
				)
			doc.custom_farm = farm
		if doc.meta.has_field("custom_purpose"):
			doc.custom_purpose = "Production"
		for row in rows:
			line = doc.append("items", {
				"item_code": row["item_code"],
				"qty": row["qty"],
				"schedule_date": wanted,
				"warehouse": warehouse,
			})
			if line.meta.has_field("custom_purpose"):
				# Free text on the line. Say what it is for in the words a store
				# keeper reading the request would use, not "livestock feed".
				line.custom_purpose = _("Herd feed — {0} days of cover").format(
					d.get("target_days") or "")
		doc.insert()

		return {
			"ok": True,
			"name": doc.name,
			"warehouse": warehouse,
			"schedule_date": str(wanted),
			"lines": len(rows),
			"farm": doc.get("custom_farm"),
			"items": [{"item_code": r["item_code"], "qty": r["qty"]} for r in rows],
		}

	return run(go, "livestock create_feed_request failed")


def _clean(items):
	"""Drop empty rows, merge repeats, refuse nonsense.

	Repeats are summed rather than refused: a screen that lets somebody add a
	feed twice means "this much in total", and two Material Request lines for
	one item is a supplier's invoice nobody can reconcile.
	"""
	totals, order = {}, []
	for row in items or []:
		code = (row.get("item_code") or "").strip()
		qty = flt(row.get("qty"))
		if not code or qty <= 0:
			continue
		if not frappe.db.exists("Item", code):
			frappe.throw(_("{0} is not an item on this site.").format(code))
		if code not in totals:
			order.append(code)
			totals[code] = 0.0
		totals[code] += qty
	return [{"item_code": code, "qty": totals[code]} for code in order]
