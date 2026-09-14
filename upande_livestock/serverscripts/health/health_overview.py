# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The health of the farm, in the few numbers and shapes that carry it."""

import frappe
from frappe.utils import add_days, add_months, flt, getdate, today

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common.health_case import (
	CLOSED_STATUSES,
	TREATING_STATUSES,
	concern,
	concern_days,
	days_open,
	stale_days,
)

#: How far back the monthly bars go by default. Thirteen so this month sits
#: beside the same month last year, which is the comparison a farm makes.
MONTHS = 13


@frappe.whitelist()
def health_overview(payload=None):
	"""The ward round, the year's shape, and what is worth worrying about.

	THE HEALTH TAB WAS A FORM. Four screens for recording things and nothing
	that answered "how is the herd?" — a farm could enter two hundred cases and
	never see that mastitis was a third of them, or that cases opened in March
	were double February's.

	Four things, because four is what fits in a glance and everything else is
	the register:

	* who is under treatment right now, and which of those files are worrying;
	* opened against closed, month by month, which is the only honest way to
	  see whether the farm is catching up or falling behind;
	* what she is being treated FOR, ranked — the one number that changes what
	  a farm does next season rather than this morning;
	* what it is costing, in drugs and in milk that did not come.

	EVERY LINE IS READ OFF RECORDS, none of it estimated. Where the record is
	silent — no response written against a treatment, no production loss
	entered — the answer says so instead of filling the gap in.
	"""

	def go():
		guard_read("Livestock Health Case")
		d = as_dict(payload) if payload else {}
		months = int(d.get("months") or MONTHS)
		since = getdate(add_months(today(), -months + 1)).replace(day=1)

		rows = frappe.get_all(
			"Livestock Health Case",
			filters=[["docstatus", "=", 1], ["opened_date", ">=", str(since)]],
			fields=["name", "animal", "animal_name", "current_herd", "case_status",
			        "opened_date", "closed_date", "severity", "provisional_diagnosis",
			        "confirmed_diagnosis", "production_loss_kg", "total_treatment_cost"],
			limit_page_length=0,
		)
		# Open files can be older than the window and still be this morning's
		# problem, so they are fetched in their own right rather than filtered
		# out of a date range.
		standing = frappe.get_all(
			"Livestock Health Case",
			filters=[["docstatus", "=", 1], ["case_status", "in", list(TREATING_STATUSES)]],
			fields=["name", "animal", "animal_name", "current_herd", "case_status",
			        "opened_date", "severity", "provisional_diagnosis"],
			order_by="opened_date asc",
			limit_page_length=0,
		)
		last = _last_treatment_dates([r.name for r in standing])

		ward = []
		for r in standing:
			case = dict(r)
			case["days_open"] = days_open(case)
			case["last_treatment_on"] = last.get(r.name)
			case["concern"] = concern(case, last.get(r.name))
			ward.append(case)
		ward.sort(key=lambda c: -(c["days_open"] or 0))

		live = frappe.db.count(
			"Animal",
			{"status": ["not in", list(RETIRED_STATUSES)], "disabled": 0},
		)
		under = len({c["animal"] for c in ward})

		return {
			"ok": True,
			"since": str(since),
			"herd_size": live,
			"under_treatment": under,
			# The share of the herd with a file open. A farm knows whether 4% is
			# normal for it; nobody knows what "eleven cases" means.
			"share": round(under * 100.0 / live, 1) if live else None,
			"ward": ward[:40],
			"worrying": [c for c in ward if c["concern"]],
			"months": _by_month(rows, since, months),
			"diagnoses": _by_diagnosis(rows),
			"severity": _by_severity(rows),
			"herds": _by_herd(rows),
			"cost": {
				"treatment": flt(sum(flt(r.total_treatment_cost) for r in rows)),
				"lost_kg": flt(sum(flt(r.production_loss_kg) for r in rows)),
				# How much of the window's cost was actually written down. A
				# total drawn from three cases out of ninety is a number that
				# should carry its own warning.
				"costed": len([r for r in rows if flt(r.total_treatment_cost)]),
				"cases": len(rows),
			},
			"concern_days": concern_days(),
			"stale_days": stale_days(),
		}

	return run(go, "livestock health_overview failed")


def _last_treatment_dates(names):
	if not names:
		return {}
	rows = frappe.db.sql(
		"""SELECT parent, MAX(treatment_date) AS last_on
		   FROM `tabLivestock Health Treatment`
		   WHERE parenttype = 'Livestock Health Case' AND parent IN %(names)s
		   GROUP BY parent""",
		{"names": tuple(names)},
		as_dict=True,
	)
	return {r.parent: (str(r.last_on) if r.last_on else None) for r in rows}


def _by_month(rows, since, months):
	"""Opened against closed, month by month.

	Two series rather than a net figure: a month that opened nine and closed
	nine is not the same farm as a month that opened none and closed none, and
	a single line would draw them identically.
	"""
	buckets = {}
	cursor = getdate(since)
	for _ in range(months):
		buckets[str(cursor)[:7]] = {"month": str(cursor)[:7], "opened": 0, "closed": 0}
		cursor = getdate(add_days(getdate(str(cursor)[:7] + "-01"), 32)).replace(day=1)
	for r in rows:
		if r.opened_date:
			key = str(r.opened_date)[:7]
			if key in buckets:
				buckets[key]["opened"] += 1
		if r.closed_date:
			key = str(r.closed_date)[:7]
			if key in buckets:
				buckets[key]["closed"] += 1
	return list(buckets.values())


def _by_diagnosis(rows):
	"""What she is being treated for, ranked, confirmed first.

	The confirmed diagnosis where there is one, the provisional where there is
	not, and "not said" counted rather than dropped — a farm whose commonest
	entry is "not said" has a recording problem, and hiding the row hides it.
	"""
	tally = {}
	for r in rows:
		key = r.confirmed_diagnosis or r.provisional_diagnosis or "__unsaid__"
		held = tally.setdefault(key, {"diagnosis": key, "cases": 0, "confirmed": 0, "open": 0})
		held["cases"] += 1
		if r.confirmed_diagnosis:
			held["confirmed"] += 1
		if r.case_status in TREATING_STATUSES:
			held["open"] += 1
	out = sorted(tally.values(), key=lambda t: -t["cases"])
	for row in out:
		if row["diagnosis"] == "__unsaid__":
			row["diagnosis"] = None
	return out[:12]


def _by_severity(rows):
	order = ["Critical", "Severe", "Moderate", "Mild"]
	tally = {s: 0 for s in order}
	unsaid = 0
	for r in rows:
		if r.severity in tally:
			tally[r.severity] += 1
		else:
			unsaid += 1
	out = [{"severity": s, "cases": tally[s]} for s in order]
	if unsaid:
		out.append({"severity": None, "cases": unsaid})
	return out


def _by_herd(rows):
	"""Where the illness is. A herd is a shed, a ration and a water trough."""
	tally = {}
	for r in rows:
		key = r.current_herd or "__none__"
		held = tally.setdefault(key, {"herd": r.current_herd, "cases": 0, "open": 0})
		held["cases"] += 1
		if r.case_status in CLOSED_STATUSES:
			continue
		held["open"] += 1
	return sorted(tally.values(), key=lambda t: -t["cases"])[:12]
