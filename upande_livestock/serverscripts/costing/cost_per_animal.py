# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Cost per animal per day — the figure the farm runs on.

For each day: feed issued to the herds, medicine issued, labour entered,
diesel the machines burned for the feedlot, and every animal on the farm; the
day's cost per animal is the four costs over the animals. Then the month
totals, and per herd the feed cost per head per day. The rules and the
arithmetic are in `_maths`; the reads in `_data`; production's figures in
`_production`.

Read-guarded on Livestock Daily Labour rather than on a role: whoever may read
the labour book may read what the herds cost. The nutritionist has no right on
it and is refused — cost is the manager's view, not the ration designer's.
"""

import frappe
from frappe import _
from frappe.utils import get_first_day, getdate, today

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.costing import _data, _maths, _production

#: A year and a day: the report is a day table, and a longer one is a
#: different question (and an expensive one) than this page asks.
MAX_DAYS = 366


def _window(from_date, to_date):
	hi = getdate(to_date) if to_date else getdate(today())
	lo = getdate(from_date) if from_date else get_first_day(hi)
	if lo > hi:
		frappe.throw(_("The start date is after the end date."))
	if (hi - lo).days + 1 > MAX_DAYS:
		frappe.throw(_("Choose at most {0} days.").format(MAX_DAYS))
	return lo, hi


def report(from_date=None, to_date=None):
	lo, hi = _window(from_date, to_date)
	days = _maths.days_between(lo, hi)

	individual_farm, individual_heads = _data.individuals(days)
	counted_heads = _data.by_number(days)
	animals = {
		d: individual_farm.get(d, 0) + sum(h.get(d, 0) for h in counted_heads.values())
		for d in days
	}
	herd_heads = {**individual_heads, **counted_heads}

	fuel = _production.fuel(lo, hi, _data.livestock_cost_centers())
	feed = _data.feed_by_herd(lo, hi)
	out = _maths.build_report(
		days,
		feed={d: sum(h.get(d, 0) for h in feed.values()) for d in days},
		medicine=_data.medicine_by_day(lo, hi),
		labour=_data.labour_by_day(lo, hi),
		fuel=fuel["by_day"],
		animals=animals,
		herd_feed=feed,
		herd_heads=herd_heads,
	)
	for row in out["days"]:
		row["diesel_litres"] = round(fuel["litres_by_day"].get(_maths.as_date(row["date"]), 0.0), 2)

	production = _production.installed()
	return {
		"ok": True,
		"from_date": str(lo),
		"to_date": str(hi),
		**out,
		"fuel_available": fuel["available"],
		"fuel_note": fuel["reason"],
		"production_installed": production,
		"machines": fuel["machines"],
		"silage": _production.silage(lo, hi) if production else None,
		"labour_rates": _data.default_rates(),
	}


@frappe.whitelist()
def cost_per_animal(from_date=None, to_date=None):
	"""Day by day from `from_date` to `to_date` (default: this month to date)."""

	def go():
		guard_read(_data.LABOUR_DOCTYPE)
		return report(from_date, to_date)

	return run(go, "livestock cost_per_animal failed")

