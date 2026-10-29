# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""When a calf is old enough to leave its mother, and where it can go.

Calves live in their dam's herd until `calf_separation_age_days` (Settings;
0 switches this off). At that age the herdsman or manager decides: a heifer
goes to the first heifer herd; a bull calf goes to the feedlot (the band its
weight fits) or is kept for breeding. Nothing moves by itself.

"Not fed its mother's ration" lives here too: a calf under the separation age
counts in the herd but not in the head the ration is made for.
"""

import frappe
from frappe.utils import add_days, date_diff, getdate, today

from upande_livestock.serverscripts.common import herd_movement, weight_bands
from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.timings import get_timing

ALERT_KIND = "Calf Separation Due"


def separation_age_days():
	return get_timing("calf_separation_age_days")


def is_suckling(date_of_birth, on=None):
	"""Under the separation age: a calf that is with its mother and not fed the herd ration."""
	limit = separation_age_days()
	if not limit or not date_of_birth:
		return False
	return date_diff(getdate(on or today()), getdate(date_of_birth)) < limit


def _label(r):
	return r.get("tag_number") or r.get("burn_name") or r.get("name")


def breeding_herds():
	return frappe.get_all("Herds", filters={"herd_class": "Breeding"}, pluck="name", order_by="name asc")


def options_for(row):
	"""Where this calf can go, by sex. See eligibility's `separation_due`."""
	if row.get("sex") == "Female":
		heifers = herd_movement.heifer_herds()
		return [{"stream": "Heifer", "herd": heifers[0] if heifers else None}]
	weight = row.get("last_weight_kg") or 0
	bands = weight_bands.fattening_bands()
	feedlot = weight_bands.band_for_weight(weight) if weight else None
	feedlot = feedlot or (bands[0]["herd"] if bands else None)
	return [
		{"stream": "Feedlot", "herd": feedlot},
		{"stream": "Breeding", "herd": None, "herds": breeding_herds()},
	]


def _calf_herds():
	"""Herds a calf can still be with its mother in: Calf herds, and mating groups."""
	return frappe.get_all(
		"Herds", filters={"herd_class": ["in", ["Calf", "Breeding"]]}, pluck="name", limit=1000)


def separation_due(animal=None):
	"""Calves at or over the separation age that have not left.

	`[{animal, label, sex, herd, dam, age_days, over_days, weight_kg, options}]`,
	oldest first. A calf stops being a calf at the age its sex is first used for
	breeding (a heifer's service age, a bull's breeding age): past that the
	inbreeding sweep watches the pair, not this list.
	"""
	limit = separation_age_days()
	if not limit:
		return []
	herds = _calf_herds()
	if not herds:
		return []
	t = getdate(today())
	filters = [
		["current_herd", "in", herds],
		["status", "not in", list(RETIRED_STATUSES)],
		["disabled", "=", 0],
		["date_of_birth", "<=", add_days(t, -limit)],
		["dam", "is", "set"],
	]
	if animal:
		filters.append(["name", "=", animal])
	rows = frappe.get_all(
		"Animal", filters=filters, limit=5000,
		fields=["name", "tag_number", "burn_name", "sex", "current_herd", "dam", "date_of_birth",
		        "last_weight_kg"])
	heifer_cap = get_timing("min_service_age_months") * 30
	bull_cap = get_timing("breeding_bull_min_age_months") * 30
	out = []
	for r in rows:
		age = date_diff(t, getdate(r.date_of_birth))
		cap = heifer_cap if r.sex == "Female" else bull_cap
		if age >= cap:
			continue
		out.append({
			"animal": r.name, "label": _label(r), "sex": r.sex, "herd": r.current_herd, "dam": r.dam,
			"age_days": age, "over_days": age - limit,
			"weight_kg": r.last_weight_kg or None, "options": options_for(r),
		})
	out.sort(key=lambda c: (-c["age_days"], c["animal"]))
	return out


# --- who is fed -----------------------------------------------------------


def head_breakdown(herd):
	"""`{animals, calves, fed, bulls, females}` for the live animals in `herd`.

	`fed` is the head the herd's ration is made for: everyone but the calves
	under the separation age. A breeding bull is one head, like a cow.
	"""
	rows = frappe.get_all(
		"Animal",
		filters={"current_herd": herd, "docstatus": ["!=", 2], "status": ["not in", RETIRED_STATUSES]},
		fields=["sex", "date_of_birth"], limit=100000)
	calves = sum(1 for r in rows if is_suckling(r.date_of_birth))
	return {
		"animals": len(rows),
		"calves": calves,
		"fed": len(rows) - calves,
		"bulls": sum(1 for r in rows if r.sex == "Male" and not is_suckling(r.date_of_birth)),
		"females": sum(1 for r in rows if r.sex == "Female" and not is_suckling(r.date_of_birth)),
	}


def fed_head_count(herd):
	return head_breakdown(herd)["fed"]
