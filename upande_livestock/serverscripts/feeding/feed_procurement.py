# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What to buy, in one order, off the projection.

YOU DO NOT BUY WHAT YOU MIX. A concentrate with a recipe of its own is made on
this farm, so running short of it is answered by a Work Order, not a purchase
order — and ordering a tonne of "Calves Meal" from a supplier who has never
heard of the farm's own formulation is the mistake this rule exists to stop.
What a short mixed concentrate really means is that its RAW MATERIALS need
buying, and the projection already counts those (see feed_projection: a raw
material's draw includes what the concentrates pull through it).

So the order covers exactly two kinds of thing:

  raw materials         silage, hay, wheat bran, maize germ, minerals
  bought-in concentrate  named on Livestock Settings, arriving ready-packed

and never a mixed concentrate. `_engine` already draws that line — it is the
same one that decides whether a shortage is answered by mixing or by buying —
so this reads it rather than inventing a second rule that could disagree.

HOW MUCH: cover to a date, not a quantity. The farm thinks in "enough to get to
the end of the month", and the arithmetic that turns that into kilograms
depends on the herd, which moves. A target in days survives a herd change; a
target in kilograms is wrong the morning after somebody splits a group.

Nothing here posts stock. A Material Request is a request — what it commits the
farm to is a conversation with a supplier, and it is deliberately left in draft
for a person to look at before it goes anywhere.
"""

import math

import frappe
from frappe import _
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard, guard_read, run
from upande_livestock.serverscripts.feeding import _engine as feeding
from upande_livestock.serverscripts.feeding.feed_projection import _draw_per_day, _on_hand

#: Buy up to this many days of cover unless told otherwise. Four weeks: long
#: enough to be worth a supplier's trip, short enough that a herd change has
#: not invalidated it before the feed arrives.
DEFAULT_TARGET_DAYS = 28


def _mixed_on_this_farm():
	"""Items the farm manufactures rather than buys.

	An item with a default BOM is made here. The bought-in list is the
	exception in the other direction — a ready-packed concentrate may also have
	a BOM on file, for costing or for a recipe the farm has stopped using, and
	the settings entry is what says the farm actually buys it.
	"""
	bought_in = feeding._bought_in_concentrates()
	mixed = set()
	for row in frappe.get_all("BOM", filters={"is_active": 1, "docstatus": 1},
	                          fields=["item"], distinct=True):
		if row.item and row.item not in bought_in:
			mixed.add(row.item)
	return mixed, bought_in


def _shortfalls(target_days):
	"""Every buyable feed that will not last `target_days`, and by how much."""
	mixed, bought_in = _mixed_on_this_farm()
	out = []
	for item_code, entry in _draw_per_day().items():
		per_day = flt(entry["direct_kg"]) + flt(entry["via_concentrate_kg"])
		if per_day <= 0:
			continue
		if item_code in mixed and item_code not in bought_in:
			# Mixed here. Its raw materials are in this same list on their own
			# account; ordering the concentrate itself would double-buy.
			continue
		on_hand = _on_hand(item_code)
		needed = per_day * target_days
		if on_hand >= needed:
			continue
		item = frappe.db.get_value(
			"Item", item_code, ["item_name", "stock_uom"], as_dict=True) or {}
		cover = on_hand / per_day if per_day else None
		out.append({
			"item_code": item_code,
			"item_name": item.get("item_name") or item_code,
			"uom": item.get("stock_uom") or "",
			"on_hand": round(on_hand, 2),
			"per_day": round(per_day, 3),
			"days_cover": round(cover, 1) if cover is not None else None,
			"runs_out_on": add_days(today(), int(cover)) if cover is not None else None,
			"target_days": target_days,
			# Rounded UP to whole units. The quantity a Material Request stores
			# is rounded by ERPNext anyway, and rounding down would order 687
			# where 687.34 was needed — a shortfall reintroduced by the
			# arithmetic meant to remove it. Nobody buys a third of a kilogram
			# of limestone.
			"order_qty": float(math.ceil(needed - on_hand)),
			"source": "Bought in" if item_code in bought_in else "Raw material",
		})
	out.sort(key=lambda r: (r["days_cover"] is None, r["days_cover"] or 0))
	return out


@frappe.whitelist()
def feed_procurement(payload=None):
	"""What the farm should buy to reach `target_days` of cover."""

	def go():
		guard_read("Item")
		d = as_dict(payload)
		target_days = max(1, min(int(d.get("target_days") or DEFAULT_TARGET_DAYS), 365))
		rows = _shortfalls(target_days)
		return {
			"ok": True,
			"target_days": target_days,
			"items": rows,
			"warehouse": _feed_store(),
			"basis": "today's head counts and today's rations",
			"open_requests": _open_requests(),
		}

	return run(go, "livestock feed_procurement failed")


def _feed_store():
	"""Where bought feed lands: the first source store the farm feeds out of."""
	rows = frappe.get_all(
		"Livestock Feed Warehouse", filters={"parenttype": "Livestock Settings"},
		fields=["warehouse"], order_by="idx asc", limit=1,
	)
	if rows and rows[0].warehouse:
		return rows[0].warehouse
	return frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse")


def _open_requests():
	"""Feed already on order, so the same shortage is not bought twice.

	Shown rather than subtracted: a Material Request raised three weeks ago and
	never followed up is not stock, and quietly netting it off would hide both
	the shortage and the fact that nobody chased the order.
	"""
	rows = frappe.db.sql(
		"""SELECT mr.name, mr.transaction_date, mr.status,
		          COUNT(i.name) AS line_count, SUM(i.qty) AS total_qty
		   FROM `tabMaterial Request` mr
		   JOIN `tabMaterial Request Item` i ON i.parent = mr.name
		   WHERE mr.docstatus < 2
		     AND mr.material_request_type = 'Purchase'
		     AND mr.status NOT IN ('Stopped', 'Cancelled')
		     AND mr.transaction_date >= %s
		     AND i.item_code IN (
		         SELECT DISTINCT item_code FROM `tabBOM Item`
		         WHERE parenttype = 'BOM')
		   GROUP BY mr.name
		   ORDER BY mr.transaction_date DESC
		   LIMIT 20""",
		(add_days(today(), -60),), as_dict=True,
	)
	return rows
