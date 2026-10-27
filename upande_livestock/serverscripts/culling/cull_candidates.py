# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which animals the figures argue against keeping, and the figures themselves."""

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, today

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.common.gain import adg_between, herd_target_adg, weights_for_many
from upande_livestock.serverscripts.common.gain import period_days as _period

#: How far back the yearly rows go.
YEARS = 5

#: Days ill in the last year before it is worth saying out loud.
SICK_DAYS_CONCERN = 21

#: Most a shortfall in gain can weigh. A shortfall of the whole target (no gain
#: at all) weighs this much; a smaller one weighs in proportion, never below
#: the floor, so any animal under target is visibly on the list.
GAIN_WEIGHT_MAX = 50
GAIN_WEIGHT_MIN = 10


@frappe.whitelist()
def cull_candidates(payload=None):
	"""Rank the animals by the case against each, worst first.

	A SUGGESTION, NEVER A DECISION. Everything here is read off records that
	already exist — weighings and health cases. No animal is culled by
	arithmetic and none is protected by it either: the list exists so the few
	worth looking at are not buried under the many that are fine, and the
	screen lets a manager raise a case against any animal at all.

	WHY EACH ONE IS HERE IS THE POINT. Every candidate carries the reasons that
	put it there, its own figures beside the herd's, and its last five years,
	so the argument can be read rather than trusted.

	The measures: average daily gain over the period (90 days by default)
	against its herd's target, and days under treatment.
	"""

	def go():
		guard_read("Animal")
		d = as_dict(payload) if payload else {}
		want = int(d.get("limit") or 25)
		days = _period(d.get("period_days"))

		animals = frappe.get_all(
			"Animal",
			filters=[["status", "not in", list(RETIRED_STATUSES)], ["disabled", "=", 0]],
			fields=["name", "burn_name", "tag_number", "current_herd", "date_of_birth", "status"],
			limit_page_length=0,
		)
		if not animals:
			return {"ok": True, "candidates": [], "considered": 0, "herd": {}, "period_days": days}

		facts = _facts([a.name for a in animals], days)
		targets = {h: herd_target_adg(h) for h in {a.current_herd for a in animals}}
		herd = _medians(animals, facts)

		out = []
		for a in animals:
			f = facts.get(a.name, _blank())
			target = targets.get(a.current_herd)
			reasons = _reasons(f, target, days)
			if not reasons:
				continue
			out.append({
				"animal": a.name,
				"name": a.tag_number or a.burn_name or a.name,
				"herd": a.current_herd,
				"status": a.status,
				"age_days": date_diff(today(), getdate(a.date_of_birth)) if a.date_of_birth else None,
				"period_adg": _round(f["period_adg"]),
				"target_adg": _round(target),
				"score": sum(r["weight"] for r in reasons),
				"reasons": reasons,
				"bars": _bars(f, target, herd),
				"years": _years(f),
			})

		out.sort(key=lambda r: (-r["score"], r["name"]))
		return {
			"ok": True,
			"candidates": out[:want],
			"considered": len(animals),
			"flagged_count": len(out),
			"herd": herd,
			"period_days": days,
		}

	return run(go, "livestock cull_candidates failed")


def _round(value, places=3):
	return None if value is None else round(flt(value), places)


def _blank():
	return {"period_adg": None, "sick_days": 0.0, "sick_days_year": 0.0, "sick_by_year": {}, "cases": 0}


def _facts(names, period_days):
	"""Everything the ranking needs, in two passes over the whole herd."""
	facts = {n: _blank() for n in names}
	year_ago = add_days(today(), -365)
	start = add_days(today(), -period_days)

	for name, points in weights_for_many(names, birth=False).items():
		facts[name]["period_adg"] = adg_between(points, start, today())

	for row in frappe.db.sql(
		"""SELECT animal, opened_date, closed_date, duration_days
		   FROM `tabLivestock Health Case`
		   WHERE docstatus = 1 AND opened_date IS NOT NULL""",
		as_dict=True,
	):
		f = facts.get(row.animal)
		if not f:
			continue
		opened = getdate(row.opened_date)
		# An open case is still costing days. Taking duration_days at face value
		# would report an animal six weeks into treatment as having been ill for
		# none, because nobody closes a case that is not over.
		if row.duration_days:
			days = flt(row.duration_days)
		elif row.closed_date:
			days = date_diff(getdate(row.closed_date), opened)
		else:
			days = date_diff(today(), opened)
		days = max(days, 0.0)
		f["cases"] += 1
		f["sick_days"] += days
		f["sick_by_year"][opened.year] = f["sick_by_year"].get(opened.year, 0.0) + days
		if opened >= getdate(year_ago):
			f["sick_days_year"] += days

	return facts


def _median(values):
	rows = sorted(v for v in values if v is not None)
	if not rows:
		return None
	mid = len(rows) // 2
	return rows[mid] if len(rows) % 2 else (rows[mid - 1] + rows[mid]) / 2.0


def _medians(animals, facts):
	"""The herd each is measured against, over the animals that have each measure.

	Median, not mean: one outlier drags a mean far enough that half the herd
	reads as below it, which is precisely the comparison this exists to make
	honest.
	"""
	gains = [facts.get(a.name, _blank())["period_adg"] for a in animals]
	sick = [facts.get(a.name, _blank())["sick_days_year"] for a in animals]
	return {"period_adg": _round(_median(gains)), "sick_days": _median(sick)}


def _reasons(facts, target, period_days):
	"""The case against it, in as many sentences as there are facts for.

	Each carries its own weight so the ranking can be read off the reasons
	rather than off a number nobody can take apart.
	"""
	out = []
	adg = facts["period_adg"]

	if adg is not None and target and adg < target:
		shortfall = (target - adg) / target
		weight = max(GAIN_WEIGHT_MIN, min(GAIN_WEIGHT_MAX, int(shortfall * GAIN_WEIGHT_MAX)))
		out.append({
			"key": "poor_gain",
			"label": f"Gaining {adg:.2f} kg/day against a target of {target:.2f}",
			"detail": f"Over the last {period_days} days." + (" It is losing weight." if adg < 0 else ""),
			"weight": weight,
		})

	if facts["sick_days_year"] >= SICK_DAYS_CONCERN:
		out.append({
			"key": "sick",
			"label": f"{int(facts['sick_days_year'])} days ill this year",
			"detail": f"Across {facts['cases']} health case"
			          f"{'' if facts['cases'] == 1 else 's'}.",
			"weight": min(35, int(facts["sick_days_year"]) // 10 * 6),
		})

	return out


def _bars(facts, target, herd):
	"""Its figures beside the herd's, for the chart."""
	out = []
	if facts["period_adg"] is not None and target:
		out.append({
			"label": "Daily gain", "hers": _round(facts["period_adg"]), "herd": _round(target),
			"unit": "kg/d", "worse": facts["period_adg"] < target,
		})
	theirs = herd.get("sick_days")
	hers = facts["sick_days_year"]
	if theirs is not None and (flt(hers) or flt(theirs)):
		out.append({
			"label": "Days ill this year", "hers": round(flt(hers), 1), "herd": round(flt(theirs), 1),
			"unit": "d", "worse": flt(hers) > flt(theirs),
		})
	return out


def _years(facts):
	"""The last five years, one row each — the days it was ill."""
	this_year = getdate(today()).year
	span = list(range(this_year - YEARS + 1, this_year + 1))
	return [{"year": y, "sick_days": int(facts["sick_by_year"].get(y, 0))} for y in span]
