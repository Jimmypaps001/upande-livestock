# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who is related to whom, close enough that they should not run together.

Parents and siblings only: sire-daughter, dam-son, full siblings (same dam and
same sire) and half siblings (same dam or same sire). An unknown parent never
matches anything — two animals both "by an unknown bull" are not half siblings.

Only the farm's own bulls are known: `Animal.sire` is a Link; `sire_name` (an
A.I. straw, an outside bull) is free text and is not compared.

Every answer here is for a WARNING. Nothing in this module blocks anything.
"""

import frappe
from frappe.utils import date_diff, getdate, today

from upande_livestock.serverscripts.common import herd_history
from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES
from upande_livestock.serverscripts.common.timings import get_timing

_FIELDS = ["name", "tag_number", "burn_name", "sex", "dam", "sire", "date_of_birth", "current_herd"]


def label(row):
	return row.get("tag_number") or row.get("burn_name") or row.get("name")


def _row(animal):
	return frappe.db.get_value("Animal", animal, _FIELDS, as_dict=True)


def _relation(a, b):
	"""Relation between two animal rows (any order), or None."""
	if not a or not b or a.name == b.name:
		return None
	if {a.sex, b.sex} != {"Female", "Male"}:
		return None
	male, female = (a, b) if a.sex == "Male" else (b, a)

	if female.sire and female.sire == male.name:
		return {"relation": "sire-daughter", "shared_parent": male.name,
		        "message": "{} is the sire of {}.".format(label(male), label(female))}
	if male.dam and male.dam == female.name:
		return {"relation": "dam-son", "shared_parent": female.name,
		        "message": "{} is the dam of {}.".format(label(female), label(male))}

	same_dam = bool(male.dam and male.dam == female.dam)
	same_sire = bool(male.sire and male.sire == female.sire)
	if same_dam and same_sire:
		return {"relation": "full-siblings", "shared_parent": female.dam,
		        "shared_parents": [female.dam, female.sire],
		        "message": "{} and {} are full siblings: both out of {} by {}.".format(
			        label(male), label(female), female.dam, female.sire)}
	if same_dam or same_sire:
		parent = female.dam if same_dam else female.sire
		how = "out of" if same_dam else "sired by"
		return {"relation": "half-siblings", "shared_parent": parent,
		        "message": "{} and {} are half-siblings: both {} {}.".format(
			        label(male), label(female), how, parent)}
	return None


def relation(a, b):
	"""`{relation, shared_parent, message}` for two animal names, or None."""
	return _relation(_row(a), _row(b))


def _age_days(row, on):
	return date_diff(getdate(on), getdate(row.date_of_birth)) if row.date_of_birth else None


def _is_calf(row, on):
	limit = get_timing("calf_separation_age_days")
	age = _age_days(row, on)
	return bool(limit) and age is not None and age < limit


def _of_breeding_age(row, on):
	"""Old enough to be a mate. An animal with no birth date is given the benefit
	of the doubt: it is a record to fix, not a mate to hide (as heat_candidates)."""
	age = _age_days(row, on)
	if age is None:
		return True
	if _is_calf(row, on):
		return False
	months = get_timing("breeding_bull_min_age_months") if row.sex == "Male" \
		else get_timing("min_service_age_months")
	return age >= months * 30


def _members(herd, on):
	if on:
		names = herd_history.members_on(herd, on)
	else:
		names = frappe.get_all(
			"Animal", filters={"current_herd": herd, "disabled": 0, "status": ["not in", list(RETIRED_STATUSES)]},
			pluck="name", limit=100000)
	return frappe.get_all("Animal", filters={"name": ["in", names or [""]]}, fields=_FIELDS, limit=100000)


def conflicts(animal, herd, on=None):
	"""Opposite-sex animals of breeding age in `herd` that `animal` is related to.

	`[{other, other_label, relation, shared_parent, message}]`. A calf under the
	separation age is not a mate, on either side of the pair.
	"""
	subject = _row(animal)
	if not subject or not herd:
		return []
	day = on or today()
	if _is_calf(subject, day):
		return []
	out = []
	for other in _members(herd, on):
		if other.name == subject.name or other.sex == subject.sex:
			continue
		if not _of_breeding_age(other, day):
			continue
		found = _relation(subject, other)
		if found:
			out.append({"other": other.name, "other_label": label(other), **found})
	out.sort(key=lambda c: (c["relation"], c["other"]))
	return out


def herd_conflicts(herd, on=None):
	"""Every related male/female pair of breeding age standing in `herd`.

	`[{male, female, relation, shared_parent, message}]` — what the nightly sweep
	raises Inbreeding Risk from, for the pairs no movement ever announced (a
	heifer growing up in her sire's herd).
	"""
	day = on or today()
	members = [m for m in _members(herd, on) if _of_breeding_age(m, day)]
	males = [m for m in members if m.sex == "Male"]
	females = [m for m in members if m.sex == "Female"]
	out = []
	for male in males:
		for female in females:
			found = _relation(male, female)
			if found:
				out.append({"male": male.name, "female": female.name, **found})
	return out
