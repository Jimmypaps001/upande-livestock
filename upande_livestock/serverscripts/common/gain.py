# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weighing history and average daily gain, as far as the Daily Feed Report needs.

A weighing history is a list of (date, kg) points. Gain over a stretch is the
last point's weight minus the first's, divided by the days between them. Fewer
than two points, or both on one day, is None, never 0: "not enough weighings"
and "did not grow" are different things.

Trimmed from Mutara's `gain.py`: its herd ranking and targets are beef-only.
"""

import frappe
from frappe.utils import flt, getdate

DEFAULT_PERIOD_DAYS = 90


def weights_for_many(animals, birth=False):
	"""{animal: [(date, kg), ...]} ascending, from submitted weight records.

	One pass for all the animals asked about. The birth weight is not part of
	the history here.
	"""
	animals = list(animals)
	out = {a: [] for a in animals}
	if not animals:
		return out
	for r in frappe.db.sql(
		"""SELECT animal, weight_date, weight_kg FROM `tabLivestock Weight Record`
		   WHERE docstatus = 1 AND animal IN %(animals)s AND weight_kg > 0
		   ORDER BY weight_date ASC, creation ASC""",
		{"animals": tuple(animals)},
		as_dict=True,
	):
		out[r.animal].append((getdate(r.weight_date), flt(r.weight_kg)))
	return out


def adg_between(points, start=None, end=None):
	"""kg/day from the first to the last point inside [start, end], or None."""
	start = getdate(start) if start else None
	end = getdate(end) if end else None
	inside = [
		(d, w) for d, w in points if (start is None or d >= start) and (end is None or d <= end)
	]
	if len(inside) < 2:
		return None
	(d0, w0), (d1, w1) = inside[0], inside[-1]
	days = (d1 - d0).days
	if days <= 0:
		return None
	return (w1 - w0) / days
