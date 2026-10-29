# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who sired a natural service: the mature bull who was in her herd around conception.

Nobody watches a bull serve in a paddock; what the farm knows is where each
animal was. A bull is a candidate when he was old enough
(`breeding_bull_min_age_months` at the conception date) and stood in the
female's herd on any day within `conception_window_days` either side of the
perceived conception date. Exactly one candidate is the sire, inferred;
several are listed for the user to choose from; none is a warning.

A sire the user picked is never second-guessed: callers use the inference only
when nobody chose.
"""

import frappe
from frappe.utils import add_days, add_months, formatdate, getdate

from upande_livestock.serverscripts.common import herd_history
from upande_livestock.serverscripts.common.timings import get_timing


def _herd_label(herd):
	return frappe.db.get_value("Herds", herd, "herd_name") or herd


def _short(date):
	return getdate(date).strftime("%d %b")


def candidate_sires(female, conception_date):
	"""Bulls that shared the female's herd around `conception_date`.

	`[{animal, label, herd, from, to, basis}]`, oldest bull first.
	"""
	day = getdate(conception_date)
	herd = herd_history.herd_on(female, day)
	if not herd:
		return []
	window = get_timing("conception_window_days")
	first, last = add_days(day, -window), add_days(day, window)
	present = herd_history.present_between(herd, first, last)
	if not present:
		return []
	min_months = get_timing("breeding_bull_min_age_months")
	rows = frappe.get_all(
		"Animal", filters={"name": ["in", list(present)], "sex": "Male"},
		fields=["name", "tag_number", "burn_name", "date_of_birth"], limit=100000)
	out = []
	for r in rows:
		if r.date_of_birth and add_months(getdate(r.date_of_birth), min_months) > day:
			continue
		start, end = present[r.name]
		label = r.tag_number or r.burn_name or r.name
		out.append({
			"animal": r.name, "label": label, "herd": herd,
			"from": str(start), "to": str(end),
			"basis": "{} was in {} from {} to {}".format(label, _herd_label(herd), _short(start), _short(end)),
		})
	out.sort(key=lambda c: (c["from"], c["animal"]))
	return out


def infer_sire(female, conception_date):
	"""`{sire, inferred, basis, candidates}` — see the module docstring."""
	candidates = candidate_sires(female, conception_date)
	if len(candidates) == 1:
		only = candidates[0]
		return {"sire": only["animal"], "inferred": True, "basis": only["basis"], "candidates": candidates}
	when = formatdate(conception_date)
	if candidates:
		names = ", ".join(c["label"] for c in candidates)
		return {"sire": None, "inferred": False, "candidates": candidates,
		        "basis": "{} bulls could be the sire around {}: {}".format(len(candidates), when, names)}
	return {"sire": None, "inferred": False, "candidates": [],
	        "basis": "No bull of breeding age was in her herd around {}".format(when)}
