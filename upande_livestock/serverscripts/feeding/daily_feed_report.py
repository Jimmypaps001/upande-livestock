# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The daily feed report: every animal fed on a day, planned against actual.

For a date (today by default), each herd that was fed shows its formula (the
components, planned and actual) and each animal in it shows planned kg a day,
actual kg a day, the variance in kg and percent, and an appetite flag (below, above or on plan; no threshold), beside
its latest weight and average daily gain so appetite can be read against
weight. The farm feeds a pen, so an animal's actual is the herd's actual kg
divided by the head fed (`feed_actuals.per_animal_intake`).

`get_daily_feed_report` is a plain python function other modules import (the
daily email does). `daily_feed_report` is the whitelisted wrapper with the
read guards.

A herd counts as fed on the day when its feed day was mixed (or is waiting for
stock), or when feed runs for it stand on that day from the older route. For
the second kind there is no record of components, so the actual is what was
issued and each component is scaled to it.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding import feed_actuals

def appetite_flag(variance_kg):
	"""No threshold: "below" the plan, "above" it, or "on_plan"."""
	return feed_actuals.appetite(variance_kg)


def _fed_day(herd, day):
	"""The herd's day with its true actual, or None when the herd was not fed."""
	info = feed_actuals.herd_day(herd, day)
	if info["status"] in ("Manufactured", "Waiting for stock"):
		return info
	bom_item = frappe.db.get_value("BOM", info["bom"], "item") if info["bom"] else None
	if not bom_item:
		return None
	runs = feed_actuals._issued_on(frappe._dict(item=bom_item), herd, day)
	issued = flt(sum(flt(r.qty) for r in runs))
	if issued <= 0:
		return None
	if not info["record"] and info["planned_kg"] > 0:
		# Fed by the older route: no components were recorded, so the issue
		# total stands as the actual and each component is scaled to it.
		ratio = issued / info["planned_kg"]
		for c in info["components"]:
			c["actual_kg"] = flt(c["planned_kg"] * ratio, feed_actuals.PRECISION)
			c["actual_per_head"] = flt(c["actual_kg"] / info["head_count"], 4) if info["head_count"] else 0.0
		info["actual_kg"] = flt(issued, feed_actuals.PRECISION)
		info["actual_per_head"] = flt(issued / info["head_count"], feed_actuals.PRECISION) if info["head_count"] else 0.0
	return info


def _weights(animals, day):
	"""{animal: (last_weight, last_weight_date, adg)} on or before `day`."""
	from upande_livestock.serverscripts.common.gain import DEFAULT_PERIOD_DAYS, adg_between, weights_for_many

	out = {}
	start = getdate(add_days(day, -DEFAULT_PERIOD_DAYS))
	for animal, points in weights_for_many(animals, birth=False).items():
		points = [p for p in points if p[0] <= day]
		if not points:
			out[animal] = (None, None, None)
			continue
		adg = adg_between(points, start, day)
		out[animal] = (points[-1][1], str(points[-1][0]), None if adg is None else round(adg, 3))
	return out


def get_daily_feed_report(date=None, herd=None):
	"""The report for `date` (default today), optionally one herd. Plain python.

	Returns `{"date", "herds": [{"herd", "herd_name", "head_count", "planned_kg",
	"actual_kg", "amended", "draft_entries", "components": [{"item_code",
	"item_name", "uom", "planned_kg", "actual_kg"}]}], "animals": [{"animal",
	"tag", "herd", "planned_kg", "actual_kg", "variance_kg", "variance_pct",
	"appetite", "last_weight", "last_weight_date", "adg"}], "totals":
	{"planned_kg", "actual_kg", "below_plan", "above_plan", "on_plan"}}`
	(the last three count animals; appetite is "below" | "above" | "on_plan",
	with no threshold: every animal shows its variance).
	"""
	day = getdate(date or today())
	filters = [["bom", "is", "set"]]
	if herd:
		filters.append(["name", "=", herd])
	herds, animals = [], []
	for h in frappe.get_all("Herds", filters=filters, pluck="name", order_by="name asc"):
		try:
			info = _fed_day(h, day)
		except frappe.ValidationError:
			continue
		if not info:
			continue
		herds.append(
			{
				"herd": info["herd"],
				"herd_name": info["herd_name"],
				"head_count": info["head_count"],
				"planned_kg": info["planned_kg"],
				"actual_kg": info["actual_kg"],
				"amended": info["amended"],
				"draft_entries": info["draft_entries"],
				"components": [
					{k: c[k] for k in ("item_code", "item_name", "uom", "planned_kg", "actual_kg")}
					for c in info["components"]
				],
			}
		)
		planned, actual = info["planned_per_head"], info["actual_per_head"]
		pct = feed_actuals.variance_pct(planned, actual)
		flag = appetite_flag(actual - planned)
		for a in _herd_animals(h, day):
			animals.append(
				{
					"animal": a["animal"],
					"tag": a["tag"],
					"herd": h,
					"planned_kg": planned,
					"actual_kg": actual,
					"variance_kg": flt(actual - planned, feed_actuals.PRECISION),
					"variance_pct": pct,
					"appetite": flag,
					"last_weight": None,
					"last_weight_date": None,
					"adg": None,
				}
			)
	weights = _weights([a["animal"] for a in animals], day)
	for a in animals:
		a["last_weight"], a["last_weight_date"], a["adg"] = weights.get(a["animal"], (None, None, None))
	return {
		"date": str(day),
		"herds": herds,
		"animals": animals,
		"totals": {
			"planned_kg": flt(sum(h["planned_kg"] for h in herds), feed_actuals.PRECISION),
			"actual_kg": flt(sum(h["actual_kg"] for h in herds), feed_actuals.PRECISION),
			"below_plan": sum(1 for a in animals if a["appetite"] == "below"),
			"above_plan": sum(1 for a in animals if a["appetite"] == "above"),
			"on_plan": sum(1 for a in animals if a["appetite"] == "on_plan"),
		},
	}


def _herd_animals(herd, day):
	return feed_actuals.per_animal_intake(herd, day)["animals"]


@frappe.whitelist()
def daily_feed_report(date=None, herd=None):
	"""Read-guarded wrapper of `get_daily_feed_report`; the same shape plus `ok`."""

	def go():
		guard_read("Herds")
		guard_read("Animal")
		out = get_daily_feed_report(date, herd)
		out["ok"] = True
		return out

	return run(go, "livestock daily_feed_report failed")
