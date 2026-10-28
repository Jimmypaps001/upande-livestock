# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Productivity trend: weekly average daily gain per herd against its target."""

import frappe
from frappe.utils import add_days, cint, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.common.gain import herd_target_adg
from upande_livestock.serverscripts.forecast import data, engine
from upande_livestock.serverscripts.performance.bull_performance import PERFORMANCE_CLASSES

# An interval's gain is credited to the week of its later weighing, so the
# earlier weighing may sit before the window: read this much further back.
LOOKBACK_DAYS = 120

FARM = "__farm__"


def _points(start, herd):
	params = {"start": str(start), "classes": PERFORMANCE_CLASSES}
	cond = ""
	if herd:
		cond = "AND w.current_herd = %(herd)s"
		params["herd"] = herd
	rows = frappe.db.sql(
		f"""SELECT w.animal, w.current_herd, w.weight_date, w.weight_kg
		    FROM `tabLivestock Weight Record` w
		    JOIN `tabHerds` h ON h.name = w.current_herd
		    WHERE w.docstatus = 1 AND w.weight_kg > 0 AND w.weight_date >= %(start)s
		      AND h.herd_class IN %(classes)s {cond}
		    ORDER BY w.weight_date ASC, w.creation ASC""",
		params,
		as_dict=True,
	)
	return [(r.animal, r.current_herd, getdate(r.weight_date), flt(r.weight_kg)) for r in rows]


def _point(row):
	return {
		"week_start": data.iso(row["week_start"]),
		"avg_adg": row["avg_adg"],
		"head": row["head"],
		"avg_weight": row["avg_weight"],
	}


@frappe.whitelist()
def get_productivity_trend(weeks=26, herd=None) -> dict:
	guard_read("Animal")
	weeks = cint(weeks) or 26
	on = getdate(today())
	start = add_days(engine.iso_week_start(on), -7 * weeks - LOOKBACK_DAYS)
	buckets = engine.trend_buckets(_points(start, herd or None), on, weeks)
	series, farm = {}, []
	for row in buckets:
		if row["herd"] == FARM:
			farm.append(_point(row))
		else:
			series.setdefault(row["herd"], []).append(_point(row))
	return {
		"series": [
			{"herd": h, "target_adg_kg": herd_target_adg(h), "points": pts}
			for h, pts in sorted(series.items())
		],
		"farm": farm,
	}
