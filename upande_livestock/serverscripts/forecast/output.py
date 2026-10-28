# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Output forecast: how many bulls, and how many kg, will be ready each week."""

import frappe
from frappe.utils import flt, getdate, today

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.forecast import data, engine


@frappe.whitelist()
def get_output_forecast(weeks=None, herd=None) -> dict:
	guard_read("Animal")
	horizon = data.horizon_weeks(weeks)
	on = getdate(today())
	bulls, unweighed = data.forecast_bulls(on, herd or None)
	rows = engine.weekly_output(bulls, on, horizon)
	return {
		"exit_weight_kg": data.exit_weight_setting(),
		"horizon_weeks": horizon,
		"weeks": [{"week_start": data.iso(r["week_start"]), "head": r["head"], "kg": r["kg"]} for r in rows],
		"bulls": [
			{
				"animal": b["animal"],
				"label": b["label"],
				"herd": b["herd"],
				"latest_weight_kg": b["latest_kg"],
				"latest_weight_date": data.iso(b["latest_date"]),
				"forecast_adg": None if b["adg"] is None else round(flt(b["adg"]), 3),
				"adg_source": b["adg_source"],
				"exit_weight_kg": b["exit_kg"],
				"ready_date": data.iso(b["ready_date"]),
				"ready_week": data.iso(engine.iso_week_start(b["ready_date"])) if b["ready_date"] else None,
			}
			for b in bulls
		],
		# A bull with no weighing, or none that gives a gain to project, has no ready date.
		"unforecastable": unweighed + sum(1 for b in bulls if b["ready_date"] is None),
	}
