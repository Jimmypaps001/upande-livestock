# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the farm will need to feed, as the herds change under it.

THE HERD IS NOT A CONSTANT, and a projection that treats it as one is answering
a question nobody asked. Today's draw times thirty days assumes the calves in
the 0-2 pen are still there next month — they are not, they will have aged into
2-4 — and that the cows in the milking herd are still milking, which the ones
calving in a fortnight are not. Feed is bought on a lead time, so the number
worth having is what the herd will look like WHEN THE FEED ARRIVES.

So this walks the herd forward a day at a time, applying every move the farm's
own rules already know about:

  the growth ladder   a calf leaves 0-2 after sixty days, 2-4 after sixty more,
                      weaners after two hundred and forty. Each animal's exit
                      is her arrival plus the rung's own limit, and the rungs
                      chain, so one calf moves three times inside a year.
  drying off          a carrying cow leaves the milking herd for the steamers a
                      set number of days before she calves.
  calving             on the day, she moves to the post-calving herd and a calf
                      arrives in the calf pen — which is a NEW MOUTH the static
                      view never counted.
  stepping down       four months in calf and she moves from the high-yield
                      herd to the low.

WHICH MAKES IT ANSWER THE QUESTION THAT PROMPTED IT. Two cows abort: their
pregnancies are no longer confirmed, so no calving is scheduled, no calf arrives
in 0-2, and the dams do not leave the milking herd. The forecast for the calf
pen falls and the milking herd's draw stays up — scenario B instead of scenario
A — without anybody editing a forecast, because the forecast was never a
document. It is read from the events every time it is asked for.

WHAT IT DOES NOT DO is guess at anything the farm has not recorded. It does not
invent services that might happen, conceptions that might take, or culls
somebody might decide on. Every animal it moves is moved by a rule against a
date already in the system. A cow with no confirmed pregnancy simply stays where
she is, which is the honest answer and not a prediction.

Read-guarded on Item: it discloses stock balances across the farm.
"""

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, today

from upande_livestock.serverscripts.common import herd_movement as hm
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.feeding.feed_projection import (
	_draw_per_day,
	_on_hand,
	_raw_per_kg,
)

DEFAULT_DAYS = 60
MAX_DAYS = 365


def _ration_of(herd):
	"""A herd's per-head daily draw, by item, in the store's own units."""
	bom = frappe.db.get_value("Herds", herd, "bom")
	if not bom:
		return {}, {}
	direct, via = {}, {}
	for row in frappe.get_all(
		"BOM Item", filters={"parent": bom}, fields=["item_code", "qty", "stock_qty", "bom_no"]
	):
		per_head = flt(row.stock_qty or row.qty)
		if per_head <= 0:
			continue
		direct[row.item_code] = direct.get(row.item_code, 0.0) + per_head
		sub = row.bom_no or frappe.db.get_value("Item", row.item_code, "default_bom")
		if not sub:
			continue
		for raw, qty in _raw_per_kg(sub).items():
			via[raw] = via.get(raw, 0.0) + qty * per_head
	return direct, via


def _populations():
	"""Who stands where today, counted the way the herd record counts."""
	rows = frappe.db.sql(
		"""SELECT current_herd AS herd, COUNT(*) AS n FROM `tabAnimal`
		   WHERE IFNULL(current_herd, '') != '' AND docstatus != 2
		     AND IFNULL(status, '') NOT IN %(retired)s AND IFNULL(disabled, 0) = 0
		   GROUP BY current_herd""",
		{"retired": tuple(hm.RETIRED_STATUSES) if hasattr(hm, "RETIRED_STATUSES") else
		 ("Dead", "Deceased", "Sold", "Culled", "Disposed", "Transferred Out")},
		as_dict=True,
	)
	return {r.herd: float(r.n) for r in rows}


def _ladder_moves(horizon_end):
	"""Every calf who climbs a rung between now and the horizon.

	Chained: a calf who leaves 0-2 in a fortnight leaves 2-4 sixty days after
	that, and both are inside a three-month window. Following only the first
	move would show the 2-4 pen filling and never emptying.
	"""
	ladder = hm.growth_ladder()
	moves = []
	for i, rung in enumerate(ladder):
		if rung["exits_on_service"] or not rung["days_in_herd"]:
			continue
		for a in frappe.get_all(
			"Animal", filters={"current_herd": rung["herd"], "disabled": 0, "status": "Active"},
			fields=["name"], limit_page_length=0,
		):
			days_in = hm.days_in_current_herd(a.name)
			if days_in is None:
				continue
			at, position = rung["days_in_herd"] - days_in, i
			while position < len(ladder) - 1:
				nxt = ladder[position + 1]
				when = add_days(today(), max(0, at))
				if getdate(when) > getdate(horizon_end):
					break
				moves.append((str(when), ladder[position]["herd"], nxt["herd"], 1.0))
				if nxt["exits_on_service"] or not nxt["days_in_herd"]:
					break
				at += nxt["days_in_herd"]
				position += 1
	return moves


def _pregnancy_moves(horizon_end):
	"""Drying off, calving, and the calf that arrives with it.

	Read off CONFIRMED pregnancies only. A service still awaiting its check
	might not have taken, and a pregnancy that ended in an abortion is no longer
	confirmed — which is exactly how an abortion rewrites this without anybody
	editing anything.
	"""
	s = hm.settings()
	steamers, post_calving = s.get("steamer_herd"), hm.post_calving_herd()
	high, low = s.get("high_yield_herd"), s.get("low_yield_herd")
	step_down = int(s.get("high_yield_days_from_conception") or 0)
	moves, births = [], []

	rows = frappe.db.sql(
		"""SELECT s.animal, s.service_date, a.current_herd
		   FROM `tabLivestock Event` s JOIN `tabAnimal` a ON a.name = s.animal
		   WHERE s.event_type = 'Service' AND s.docstatus = 1
		     AND s.pregnancy_confirmation_status = 'Confirmed'
		     AND IFNULL(a.disabled, 0) = 0 AND IFNULL(a.status, '') = 'Active'
		     AND NOT EXISTS (
		         SELECT 1 FROM `tabLivestock Event` c
		         WHERE c.animal = s.animal AND c.docstatus = 1
		           AND c.event_type IN ('Calving', 'Abortion')
		           AND c.event_date >= s.service_date)""",
		as_dict=True,
	)
	for r in rows:
		herd = r.current_herd
		calving = hm.expected_calving_date(r.service_date)
		if not calving:
			continue
		dry_lead = hm.steamer_days_for(herd)

		if high and low and step_down and herd == high:
			when = add_days(getdate(r.service_date), step_down)
			if today() <= str(when) <= str(horizon_end):
				moves.append((str(when), high, low, 1.0))
				herd = low

		if steamers and herd != steamers and dry_lead:
			when = add_days(getdate(calving), -dry_lead)
			if today() <= str(when) <= str(horizon_end):
				moves.append((str(when), herd, steamers, 1.0))
				herd = steamers

		if str(calving) <= str(horizon_end) and post_calving:
			if herd and herd != post_calving:
				moves.append((str(calving), herd, post_calving, 1.0))
			# A calf's sex is not known until she is born, and the two sexes go
			# to different pens. Half a calf in each is the expected value, not
			# a fudge — and it is the only honest answer before the day.
			for sex in ("Female", "Male"):
				pen = hm.calf_herd(sex)
				if pen:
					births.append((str(calving), pen, 0.5))
	return moves, births


@frappe.whitelist()
def feed_forecast(payload=None):
	"""Feed needed per day ahead, as the herds change under it."""

	def go():
		guard_read("Item")
		d = as_dict(payload)
		days = max(1, min(int(d.get("days") or DEFAULT_DAYS), MAX_DAYS))
		start = today()
		end = add_days(start, days)
		dates = [add_days(start, i) for i in range(days + 1)]

		populations = _populations()
		rations = {h: _ration_of(h) for h in frappe.get_all("Herds", pluck="name")}

		preg_moves, births = _pregnancy_moves(end)
		moves = _ladder_moves(end) + preg_moves
		by_day = {}
		for when, frm, to, n in moves:
			by_day.setdefault(when, []).append(("move", frm, to, n))
		for when, pen, n in births:
			by_day.setdefault(when, []).append(("birth", None, pen, n))

		per_item, herd_series, events = {}, {}, []
		for index, day in enumerate(dates):
			# The day's moves happen before the day's feeding: a calf who leaves
			# 0-2 this morning is fed in 2-4 tonight.
			for kind, frm, to, n in by_day.get(day, []):
				if kind == "move" and frm:
					populations[frm] = max(0.0, populations.get(frm, 0.0) - n)
				populations[to] = populations.get(to, 0.0) + n
			for herd, heads in populations.items():
				herd_series.setdefault(herd, []).append(round(heads, 2))
			for item, qty in _draw_on(populations, rations).items():
				per_item.setdefault(item, [0.0] * len(dates))
				per_item[item][index] += qty
			if by_day.get(day):
				events.append({
					"on": day,
					"what": [
						{"kind": k, "from_herd": f, "to_herd": t, "heads": n}
						for k, f, t, n in by_day[day]
					],
				})

		return {
			"ok": True,
			"start": start,
			"days": days,
			"dates": dates,
			"items": _item_rows(per_item, dates),
			"events": events,
			"herds": {h: v for h, v in herd_series.items() if any(v)},
			"basis": (
				"today's herds, moved forward by the farm's own rules — the growth "
				"ladder, drying off, calving and the calves that arrive with it"
			),
		}

	return run(go, "livestock feed_forecast failed")


def _draw_on(populations, rations):
	"""Every feed drawn on one day, at that day's head counts."""
	out = {}
	for herd, heads in populations.items():
		if heads <= 0:
			continue
		direct, via = rations.get(herd) or ({}, {})
		for item, per_head in direct.items():
			out[item] = out.get(item, 0.0) + per_head * heads
		for item, per_head in via.items():
			out[item] = out.get(item, 0.0) + per_head * heads
	return out


def _item_rows(per_item, dates):
	"""Each feed: what is on hand, what it is drawn at, and when it runs out."""
	rows = []
	for item_code, series in per_item.items():
		on_hand = _on_hand(item_code)
		left, runs_out = on_hand, None
		for i, qty in enumerate(series):
			left -= qty
			if left <= 0 and runs_out is None:
				runs_out = dates[i]
		meta = frappe.db.get_value(
			"Item", item_code, ["item_name", "stock_uom"], as_dict=True) or {}
		today_draw = series[0] if series else 0.0
		last_draw = series[-1] if series else 0.0
		rows.append({
			"item_code": item_code,
			"item_name": meta.get("item_name") or item_code,
			"uom": meta.get("stock_uom") or "",
			"on_hand": round(on_hand, 2),
			"per_day": round(today_draw, 3),
			"per_day_at_horizon": round(last_draw, 3),
			# What the static view misses: the draw is not the same number in a
			# month, and this says by how much.
			"drift": round(last_draw - today_draw, 3),
			"needed_total": round(sum(series), 2),
			"runs_out_on": runs_out,
			"series": [round(q, 3) for q in series],
			"remaining": _remaining(on_hand, series),
		})
	rows.sort(key=lambda r: (r["runs_out_on"] is None, r["runs_out_on"] or ""))
	return rows


def _remaining(on_hand, series):
	"""Stock left on each day ahead, floored at nothing — a store stops."""
	left, out = on_hand, []
	for qty in series:
		left = max(0.0, left - qty)
		out.append(round(left, 2))
	return out
