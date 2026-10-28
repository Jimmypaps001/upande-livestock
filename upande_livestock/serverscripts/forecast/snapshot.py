# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weekly snapshot of the output forecast, kept so accuracy can be measured later."""

import frappe
from frappe.utils import cint, getdate, today

from upande_livestock.serverscripts.forecast import data, engine

DOCTYPE = "Livestock Forecast Snapshot"


def take_weekly_snapshot() -> int:
	"""Write today's forecast for the farm and each herd; returns the rows written.

	Idempotent per day: rows already written for today are replaced, so a
	re-run (or a manual one) never doubles anything.
	"""
	on = getdate(today())
	horizon = data.horizon_weeks()
	bulls, _unweighed = data.forecast_bulls(on)

	groups = [(None, bulls)]
	herds = sorted({b["herd"] for b in bulls})
	groups += [(h, [b for b in bulls if b["herd"] == h]) for h in herds]

	frappe.db.delete(DOCTYPE, {"snapshot_date": str(on)})
	written = 0
	for herd, members in groups:
		for row in engine.weekly_output(members, on, horizon):
			frappe.get_doc({
				"doctype": DOCTYPE,
				"snapshot_date": on,
				"week_start": row["week_start"],
				"herd": herd,
				"forecast_head": cint(row["head"]),
				"forecast_kg": row["kg"],
			}).insert(ignore_permissions=True)
			written += 1
	return written
