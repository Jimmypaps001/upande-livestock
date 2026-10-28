# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Commitment cover: does the forecast output meet what buyers have asked for?"""

import frappe
from frappe.utils import getdate, today

from upande_livestock.serverscripts.common.envelope import guard_read
from upande_livestock.serverscripts.forecast import data, engine


@frappe.whitelist()
def get_commitment_cover(weeks=None) -> dict:
	guard_read("Animal")
	guard_read("Livestock Buyer Commitment")
	horizon = data.horizon_weeks(weeks)
	on = getdate(today())
	bulls, _unweighed = data.forecast_bulls(on)
	output = engine.weekly_output(bulls, on, horizon)
	first = output[0]["week_start"] if output else engine.iso_week_start(on)
	last = output[-1]["week_start"] if output else first
	commitments = data.open_commitments(first, last)
	rows = engine.cover(output, commitments)
	return {"weeks": [{**r, "week_start": data.iso(r["week_start"])} for r in rows]}
