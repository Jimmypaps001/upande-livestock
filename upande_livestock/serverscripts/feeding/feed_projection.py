# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the farm has, what it draws a day, and the date each feed runs out.

THE QUESTION IS "WHEN", NOT "HOW MUCH". A store report that says 3,200 kg of
silage tells nobody anything: it is eleven days for this herd structure and
three weeks for last month's. The farm buys and cuts on a lead time, so the
only number worth putting on a screen is a date.

DRAW IS COUNTED TWICE OVER, ON PURPOSE. A raw material leaves the store two
ways and both are real:

  directly   wheat bran is not in any TMR, but hay and silage are — a line on
             the herd's ration, drawn every morning.
  through a  the same wheat bran is 280 kg of every tonne of calves meal, and
  concentrate the calves eat 2 kg of calves meal a head a day.

Counting only the first says the farm will never run out of wheat bran.
Counting only the second says it will never run out of hay. `_engine` runs Work
Orders with `use_multi_level_bom = 0`, so the concentrate is consumed AS STOCK
and had to be mixed first — which is exactly why both draws are real and have
to be added.

WHAT THIS DELIBERATELY DOES NOT DO is predict the future herd. Head counts move
— calves are born, cows are culled, a group is split — and a projection that
tried to model that would be a forecast of a forecast. This answers "at today's
herd and today's rations", which is the assumption a person can actually check,
and it says so on the screen.

Read-guarded on Item: it discloses stock balances across the farm.
"""

import frappe
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.feeding import _engine as feeding

DEFAULT_HORIZON = 30

#: Beyond this, "days of cover" stops being a useful number and starts being
#: arithmetic on a rounding error — a feed drawn at 0.2 kg a day would report
#: cover measured in years. Reported as None, which the screen reads as "not
#: worth worrying about".
MAX_USEFUL_DAYS = 3650


def _draw_per_day():
	"""Every feed item the farm draws in a day, and how much of it.

	Returns item_code -> {direct, through_concentrate, herds}. Both figures are
	in the item's own stock units, because that is what the store holds and
	what "on hand" is counted in.
	"""
	draw = {}

	def bucket(item_code):
		return draw.setdefault(item_code, {
			"item_code": item_code, "direct_kg": 0.0, "via_concentrate_kg": 0.0,
			"herds": [], "concentrates": [],
		})

	for herd in frappe.get_all("Herds", filters=[["bom", "is", "set"]], pluck="name"):
		try:
			_doc, bom, heads = feeding._herd_bom(herd)
		except Exception:
			# A herd whose BOM has gone, or which has none. Not this endpoint's
			# business to complain about; feed_day_status is where that shows.
			continue
		if not heads:
			continue
		for row in frappe.get_all(
			"BOM Item", filters={"parent": bom.name},
			fields=["item_code", "qty", "stock_qty", "bom_no"],
		):
			per_day = flt(row.stock_qty or row.qty) * heads
			if per_day <= 0:
				continue
			entry = bucket(row.item_code)
			entry["direct_kg"] += per_day
			entry["herds"].append({"herd": herd, "heads": heads,
			                       "per_head": flt(row.stock_qty or row.qty), "per_day": per_day})

			# A concentrate is a line with a recipe of its own. Follow it down
			# to the raw materials it is mixed from — they leave the same store.
			sub = row.bom_no or frappe.db.get_value("Item", row.item_code, "default_bom")
			if not sub:
				continue
			for raw, qty in _raw_per_kg(sub).items():
				raw_entry = bucket(raw)
				raw_entry["via_concentrate_kg"] += qty * per_day
				raw_entry["concentrates"].append(
					{"concentrate": row.item_code, "per_day": qty * per_day})
	return draw


def _raw_per_kg(bom_no):
	"""Raw material per ONE unit of what this recipe makes.

	Divided by the batch size rather than taken raw: a concentrate BOM makes a
	tonne, and its lines are for the tonne. The caller multiplies by the
	kilograms the herds actually eat.
	"""
	batch = flt(frappe.db.get_value("BOM", bom_no, "quantity")) or 1.0
	out = {}
	for row in frappe.get_all("BOM Item", filters={"parent": bom_no},
	                          fields=["item_code", "qty", "stock_qty"]):
		out[row.item_code] = out.get(row.item_code, 0.0) + flt(row.stock_qty or row.qty) / batch
	return out


def _on_hand(item_code):
	return flt(frappe.db.sql(
		"SELECT IFNULL(SUM(actual_qty), 0) FROM tabBin WHERE item_code = %s", (item_code,)
	)[0][0])


@frappe.whitelist()
def feed_projection(payload=None):
	"""Every feed, its cover in days, and the day it runs out."""

	def go():
		guard_read("Item")
		d = as_dict(payload)
		horizon = max(1, min(int(d.get("days") or DEFAULT_HORIZON), 365))
		start = today()

		rows = []
		for item_code, entry in _draw_per_day().items():
			per_day = flt(entry["direct_kg"]) + flt(entry["via_concentrate_kg"])
			on_hand = _on_hand(item_code)
			item = frappe.db.get_value(
				"Item", item_code, ["item_name", "stock_uom"], as_dict=True) or {}
			days = (on_hand / per_day) if per_day > 0 else None
			if days is not None and days > MAX_USEFUL_DAYS:
				days = None
			rows.append({
				"item_code": item_code,
				"item_name": item.get("item_name") or item_code,
				"uom": item.get("stock_uom") or "",
				"on_hand": round(on_hand, 2),
				"per_day": round(per_day, 3),
				"direct_per_day": round(flt(entry["direct_kg"]), 3),
				"via_concentrate_per_day": round(flt(entry["via_concentrate_kg"]), 3),
				"days_cover": round(days, 1) if days is not None else None,
				"runs_out_on": add_days(start, int(days)) if days is not None else None,
				"within_horizon": days is not None and days <= horizon,
				"herds": entry["herds"],
				"concentrates": entry["concentrates"],
				# The line a chart draws: stock left on each day ahead, floored
				# at nothing. A store does not go negative; it stops.
				"series": [round(max(on_hand - per_day * day, 0.0), 2)
				           for day in range(horizon + 1)],
			})

		rows.sort(key=lambda r: (r["days_cover"] is None, r["days_cover"] or 0))
		return {
			"ok": True,
			"start": start,
			"days": horizon,
			"dates": [add_days(start, day) for day in range(horizon + 1)],
			"items": rows,
			"running_out": [r for r in rows if r["within_horizon"]],
			# Said on the screen, because it is the assumption the whole
			# projection rests on and the one a person can check.
			"basis": "today's head counts and today's rations",
		}

	return run(go, "livestock feed_projection failed")
