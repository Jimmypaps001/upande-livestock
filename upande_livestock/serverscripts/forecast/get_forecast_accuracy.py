# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Forecast accuracy: what a past snapshot predicted against what actually left."""

import frappe
from frappe.utils import add_days, cint, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.forecast import data, engine


def _forecast_for(week, herd):
	"""(snapshot_date, head, kg) from the latest snapshot taken before `week` that covers it."""
	row = frappe.db.sql(
		"""SELECT snapshot_date, forecast_head, forecast_kg FROM `tabLivestock Forecast Snapshot`
		   WHERE week_start = %s AND snapshot_date < %s AND IFNULL(herd, '') = %s
		   ORDER BY snapshot_date DESC LIMIT 1""",
		(str(week), str(week), herd or ""),
	)
	return (row[0][0], row[0][1], row[0][2]) if row else (None, None, None)


@frappe.whitelist()
def get_forecast_accuracy(weeks=12, herd=None) -> dict:
	guard_read("Animal")
	weeks = cint(weeks) or 12
	herd = herd or None
	this_week = engine.iso_week_start(getdate(today()))
	out = []
	# Only completed weeks: the current one is still happening.
	for i in range(weeks, 0, -1):
		week = add_days(this_week, -7 * i)
		snap_date, f_head, f_kg = _forecast_for(week, herd)
		a_head, a_kg = data.disposal_actuals(week, herd)
		out.append({
			"week_start": data.iso(week),
			"snapshot_date": data.iso(snap_date),
			"forecast_head": f_head,
			"actual_head": a_head,
			"forecast_kg": None if f_kg is None else flt(f_kg),
			"actual_kg": a_kg,
			"error_pct_head": engine.error_pct(a_head, f_head),
			"error_pct_kg": engine.error_pct(a_kg, None if f_kg is None else flt(f_kg)),
		})
	return {"weeks": out}
