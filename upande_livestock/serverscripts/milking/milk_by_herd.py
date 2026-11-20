# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Milk yield over time, one series per herd, for the Milking dashboard chart."""

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run

MAX_DAYS = 400


def window(from_date, to_date):
	"""The (start, end) dates, defaulting to the last 30 days, never more than MAX_DAYS."""
	end = getdate(to_date) if to_date else getdate(today())
	start = getdate(from_date) if from_date else add_days(end, -29)
	if start > end:
		start, end = end, start
	if date_diff(end, start) >= MAX_DAYS:
		start = add_days(end, -(MAX_DAYS - 1))
	return start, end


def build(rows, start, end):
	"""Fold Milk Recording rows into per-herd daily series.

	Every day in the window is present for every herd that milked in it (0 when it
	did not), so the chart's lines share one x axis. Per-cow is the day's yield
	over the cows milked, the larger milking of the day (cows are milked more than
	once a day, so summing the cows would count each twice).
	"""
	days = [str(add_days(start, i)) for i in range(date_diff(end, start) + 1)]
	herds = {}
	for r in rows:
		h = herds.setdefault(r["herd"], {})
		d = h.setdefault(str(r["recording_date"]), {"kg": 0.0, "cows": 0})
		d["kg"] += flt(r["net_yield_kg"])
		d["cows"] = max(d["cows"], int(r["cows_milked"] or 0))
	series = []
	for herd in sorted(herds):
		kg, per_cow = [], []
		for day in days:
			d = herds[herd].get(day)
			kg.append(round(d["kg"], 1) if d else 0)
			per_cow.append(round(d["kg"] / d["cows"], 2) if d and d["cows"] else None)
		series.append({"herd": herd, "kg": kg, "per_cow": per_cow, "total_kg": round(sum(kg), 1)})
	return {"days": days, "herds": series}


@frappe.whitelist()
def milk_by_herd(from_date=None, to_date=None):
	def go():
		guard_read("Milk Recording")
		start, end = window(from_date, to_date)
		rows = frappe.get_all(
			"Milk Recording",
			filters={"docstatus": 1, "recording_date": ["between", [start, end]]},
			fields=["herd", "recording_date", "net_yield_kg", "cows_milked"],
			limit_page_length=0,
		)
		return {"ok": True, **build(rows, start, end)}

	return run(go, "livestock milk_by_herd failed")
