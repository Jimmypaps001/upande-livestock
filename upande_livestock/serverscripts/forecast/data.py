# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Reads that feed the production forecast: the bulls, their gain, the settings
and the commitments. The maths lives in engine.py (pure); this is the part that
talks to the database."""

import frappe
from frappe.utils import add_days, flt, getdate

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.gain import adg_between, period_days, weights_for_many
from upande_livestock.serverscripts.common.timings import get_timing, read_setting
from upande_livestock.serverscripts.common.weight_bands import fattening_bands
from upande_livestock.serverscripts.forecast import engine

DEFAULT_EXIT_KG = 450.0
FORECAST_CLASSES = ("Fattening", "Calf")
EXIT_TYPES = ("Sold", "Slaughtered")


def iso(value):
	"""An ISO date string, or None."""
	return str(value) if value else None


def exit_weight_setting():
	"""The farm-wide exit weight; the default when unset or not positive."""
	value = flt(read_setting("target_exit_weight_kg"))
	return value if value > 0 else DEFAULT_EXIT_KG


def horizon_weeks(weeks=None):
	"""Weeks to look ahead: the asked-for number when positive, else the setting."""
	try:
		asked = int(weeks)
	except (TypeError, ValueError):
		asked = 0
	return asked if asked > 0 else get_timing("forecast_horizon_weeks")


def exit_weight_for_herd(herd, bands=None):
	"""The kg a bull in `herd` is ready at.

	The top Fattening band's upper limit when `herd` is that band and it has
	one — the band ladder already says "above this, it is ready for exit" — else
	the farm setting.
	"""
	bands = fattening_bands() if bands is None else bands
	if bands and bands[-1]["herd"] == herd and bands[-1]["max_kg"]:
		return bands[-1]["max_kg"]
	return exit_weight_setting()


def _own_target(herd):
	"""The herd's own target ADG (kg/day) or None. The farm target is passed separately."""
	value = flt(frappe.db.get_value("Herds", herd, "target_adg_kg")) if herd else 0
	return value if value > 0 else None


def _farm_target():
	grams = flt(frappe.db.get_single_value("Livestock Settings", "custom_target_growth_gday"))
	return grams / 1000 if grams > 0 else None


def forecast_bulls(today, herd=None):
	"""(bulls, unweighed): every active male in a Fattening or Calf herd.

	`bulls` are those with a submitted weight, each a dict carrying what
	engine.weekly_output needs plus the display fields; `unweighed` counts the
	active males with no submitted weighing, who cannot be forecast at all.
	Bulls are ordered by ready date, those with none last.
	"""
	today = getdate(today)
	herds = {
		r.name: r.herd_class
		for r in frappe.get_all(
			"Herds", filters={"herd_class": ["in", list(FORECAST_CLASSES)]}, fields=["name", "herd_class"]
		)
	}
	if herd:
		herds = {k: v for k, v in herds.items() if k == herd}
	if not herds:
		return [], 0
	rows = frappe.get_all(
		"Animal",
		filters={
			"current_herd": ["in", list(herds)],
			"sex": "Male",
			"disabled": 0,
			"status": ["not in", list(RETIRED_STATUSES)],
		},
		fields=["name", "tag_number", "burn_name", "current_herd"],
		limit=5000,
	)
	history = weights_for_many([r.name for r in rows], birth=False)
	window_start = add_days(today, -period_days(None))

	own_adg = {r.name: adg_between(history[r.name], window_start, today) for r in rows}
	by_herd = {}
	for r in rows:
		if own_adg[r.name] is not None:
			by_herd.setdefault(r.current_herd, []).append(own_adg[r.name])
	herd_avg = {h: sum(v) / len(v) for h, v in by_herd.items()}

	bands = fattening_bands()
	farm_target = _farm_target()
	targets, exits = {}, {}
	bulls, unweighed = [], 0
	for r in rows:
		points = history[r.name]
		if not points:
			unweighed += 1
			continue
		h = r.current_herd
		if h not in targets:
			targets[h] = _own_target(h)
			exits[h] = exit_weight_for_herd(h, bands)
		adg, source = engine.forecast_adg(own_adg[r.name], herd_avg.get(h), targets[h], farm_target)
		latest_date, latest_kg = points[-1]
		ready = engine.ready_date(latest_kg, latest_date, adg, exits[h], today)
		bulls.append({
			"animal": r.name,
			"label": r.tag_number or r.burn_name or r.name,
			"herd": h,
			"latest_kg": latest_kg,
			"latest_date": latest_date,
			"adg": adg,
			"adg_source": source,
			"exit_kg": exits[h],
			"ready_date": ready,
		})
	bulls.sort(key=lambda b: (b["ready_date"] is None, b["ready_date"] or today, b["label"]))
	return bulls, unweighed


def open_commitments(first_week=None, last_week=None):
	"""Open Livestock Buyer Commitments as engine rows, oldest week first."""
	filters = {"status": "Open"}
	if first_week:
		filters["week_start"] = [">=", first_week]
	rows = frappe.get_all(
		"Livestock Buyer Commitment",
		filters=filters,
		fields=["name", "customer", "week_start", "head", "committed_kg"],
		order_by="week_start asc, creation asc",
	)
	out = []
	for r in rows:
		week = getdate(r.week_start)
		if last_week and week > getdate(last_week):
			continue
		out.append({
			"week_start": week,
			"head": r.head or 0,
			"kg": flt(r.committed_kg) or None,
		})
	return out


def disposal_actuals(week_start, herd=None):
	"""(head, kg) of submitted Sold and Slaughtered disposals dated in the week.

	With `herd`, only animals now recorded in that herd.
	"""
	start = getdate(week_start)
	params = {"start": str(start), "end": str(add_days(start, 6)), "types": EXIT_TYPES}
	join, cond = "", ""
	if herd:
		join = "JOIN `tabAnimal` a ON a.name = d.animal"
		cond = "AND a.current_herd = %(herd)s"
		params["herd"] = herd
	row = frappe.db.sql(
		f"""SELECT COUNT(*), COALESCE(SUM(d.exit_weight_kg), 0) FROM `tabLivestock Disposal` d {join}
		    WHERE d.docstatus = 1 AND d.disposal_type IN %(types)s
		      AND d.disposal_date BETWEEN %(start)s AND %(end)s {cond}""",
		params,
	)[0]
	return int(row[0] or 0), flt(row[1])
