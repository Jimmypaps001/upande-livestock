# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Average daily gain (ADG), the one number a beef farm ranks its animals on.

A weighing history is a list of (date, kg) points. Gain over a stretch is the
last point's weight minus the first's, divided by the days between them. A
stretch with fewer than two points, or with both points on one day, has no
gain: the answer is None, never 0 — "not enough weighings" and "did not grow"
are different things and the screens show them differently.

Birth weight, when the animal has both a birth date and a birth weight, is the
first point of its history, which is what makes lifetime ADG possible before
its first weighing on the farm.
"""

import frappe
from frappe.utils import flt, getdate


DEFAULT_PERIOD_DAYS = 90


def period_days(value):
	"""A ranking window in days: the value if it is a positive whole number, else the default."""
	try:
		days = int(value)
	except (TypeError, ValueError):
		days = DEFAULT_PERIOD_DAYS
	return days if days > 0 else DEFAULT_PERIOD_DAYS


def latest_weight(animal, on_date=None):
	"""Kg of the latest weighing on or before `on_date` (today by default), else None."""
	on = getdate(on_date)
	points = [p for p in weights_for(animal) if p[0] <= on]
	return points[-1][1] if points else None


def weights_for_many(animals, herd=None, birth=True):
	"""{animal: [(date, kg), ...]} ascending, for every animal asked about.

	One pass for all of them — a herd of two hundred is two queries, not four
	hundred. Only submitted weight records count; the birth point leads the
	list when the animal has both a date of birth and a birth weight. With
	`herd`, only weighings recorded while the animal was in that herd are kept
	and the birth point is left out (it belongs to no herd of ours); so is it
	with `birth=False`.
	"""
	animals = list(animals)
	out = {a: [] for a in animals}
	if not animals:
		return out

	conditions = "docstatus = 1 AND animal IN %(animals)s AND weight_kg > 0"
	params = {"animals": tuple(animals)}
	if herd:
		conditions += " AND current_herd = %(herd)s"
		params["herd"] = herd
	for r in frappe.db.sql(
		f"""SELECT animal, weight_date, weight_kg FROM `tabLivestock Weight Record`
		    WHERE {conditions} ORDER BY weight_date ASC, creation ASC""",
		params,
		as_dict=True,
	):
		out[r.animal].append((getdate(r.weight_date), flt(r.weight_kg)))

	if birth and not herd:
		for r in frappe.db.sql(
			"""SELECT name, date_of_birth, birth_weight_kg FROM `tabAnimal`
			   WHERE name IN %(animals)s AND date_of_birth IS NOT NULL AND birth_weight_kg > 0""",
			{"animals": tuple(animals)},
			as_dict=True,
		):
			out[r.name].insert(0, (getdate(r.date_of_birth), flt(r.birth_weight_kg)))
	return out


def weights_for(animal):
	"""One animal's (date, kg) history, ascending, birth weight first when known."""
	return weights_for_many([animal])[animal]


def adg_between(points, start=None, end=None):
	"""kg/day from the first to the last point inside [start, end], or None.

	Either bound may be None for "unbounded". None with fewer than two points
	in the window, or when they all fall on the same day.
	"""
	start = getdate(start) if start else None
	end = getdate(end) if end else None
	inside = [
		(d, w) for d, w in points
		if (start is None or d >= start) and (end is None or d <= end)
	]
	if len(inside) < 2:
		return None
	(d0, w0), (d1, w1) = inside[0], inside[-1]
	days = (d1 - d0).days
	if days <= 0:
		return None
	return (w1 - w0) / days


def herd_target_adg(herd):
	"""The herd's target ADG in kg/day, else the farm's (g/day / 1000), else None."""
	target = flt(frappe.db.get_value("Herds", herd, "target_adg_kg")) if herd else 0
	if target > 0:
		return target
	farm = flt(frappe.db.get_single_value("Livestock Settings", "custom_target_growth_gday"))
	return farm / 1000 if farm > 0 else None


def herd_period_gain(herd, start, end):
	"""(average ADG, animals weighed) for `herd` between two dates, inclusive.

	Uses the weighings recorded while the animals were in that herd, so a
	period reads the gain made on that herd's ration and not the gain an animal
	brought from elsewhere. An animal needs two weighings in the window to
	count; with none that do, the average is None and the head count 0.
	"""
	by_animal = {}
	for r in frappe.db.sql(
		"""SELECT animal, weight_date, weight_kg FROM `tabLivestock Weight Record`
		   WHERE docstatus = 1 AND current_herd = %s AND weight_kg > 0
		     AND weight_date BETWEEN %s AND %s
		   ORDER BY weight_date ASC, creation ASC""",
		(herd, str(start), str(end)),
		as_dict=True,
	):
		by_animal.setdefault(r.animal, []).append((getdate(r.weight_date), flt(r.weight_kg)))
	gains = [g for g in (adg_between(p) for p in by_animal.values()) if g is not None]
	if not gains:
		return None, 0
	return sum(gains) / len(gains), len(gains)
