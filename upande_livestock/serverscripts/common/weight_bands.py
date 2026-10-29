# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The weight ladder: Fattening herds are bands, and an animal belongs in the
band its latest weight falls in.

A band is [min_kg, max_kg) — an animal at exactly 250 kg is in the band that
STARTS at 250, not the one that ends there. The top band may have no upper limit.
Limits live on the Herds, never in this file; a farm that edits a band moves the
suggestions with it.

A calf is NOT placed by weight. With the first band starting at 0 kg every
weighed bull calf would be flagged at once; calves leave their mothers by AGE
(common/calf_separation), and feedlot bulls move up the ladder by weight.
"""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.animal import RETIRED_STATUSES

MOVE_DUE = "Weight Band Move Due"
READY_FOR_EXIT = "Ready for Exit"


def fattening_bands():
	"""Fattening herds as bands, lowest first. `max_kg` is None when open-ended."""
	rows = frappe.get_all(
		"Herds",
		filters={"herd_class": "Fattening"},
		fields=["name", "min_weight_kg", "max_weight_kg"],
	)
	bands = [
		{"herd": r.name, "min_kg": flt(r.min_weight_kg), "max_kg": flt(r.max_weight_kg) or None}
		for r in rows
	]
	bands.sort(key=lambda b: (b["min_kg"], b["herd"]))
	return bands


def _contains(band, weight_kg):
	return weight_kg >= band["min_kg"] and (band["max_kg"] is None or weight_kg < band["max_kg"])


def band_for_weight(weight_kg):
	"""The herd whose band holds this weight, or None (below the lowest band,
	above a closed top band, or no bands at all)."""
	weight_kg = flt(weight_kg)
	for band in fattening_bands():
		if _contains(band, weight_kg):
			return band["herd"]
	return None


def _label(row):
	return row.get("tag_number") or row.get("burn_name") or row.get("name")


_ANIMAL_FIELDS = ["name", "tag_number", "burn_name", "current_herd", "last_weight_kg", "sex"]


def _check(row, herd_classes, bands):
	"""band_check for one animal row, with the bands already read."""
	weight = flt(row.get("last_weight_kg"))
	herd = row.get("current_herd")
	if weight <= 0 or not herd or not bands:
		return None
	cls = herd_classes.get(herd)
	base = {"animal": row["name"], "label": _label(row), "herd": herd, "weight_kg": weight}

	def destination(w):
		return next((b["herd"] for b in bands if _contains(b, w)), None)

	if cls == "Fattening":
		own = next((b for b in bands if b["herd"] == herd), None)
		if own is None or _contains(own, weight):
			return None
		top = bands[-1]
		if top["max_kg"] is not None and weight >= top["max_kg"]:
			return {**base, "kind": READY_FOR_EXIT, "to_herd": None,
			        "from_min_kg": own["min_kg"], "from_max_kg": own["max_kg"]}
		return {**base, "kind": MOVE_DUE, "to_herd": destination(weight),
		        "from_min_kg": own["min_kg"], "from_max_kg": own["max_kg"]}

	return None


def _classes():
	return {
		r.name: r.herd_class
		for r in frappe.get_all("Herds", filters={"herd_class": "Fattening"},
		                        fields=["name", "herd_class"])
	}


def band_check(animal):
	"""Does this animal's latest weight say it belongs somewhere else?

	Only active animals in a Fattening herd with a weight on record are
	judged; anything else is None, as is an animal in the right band.
	"""
	row = frappe.db.get_value("Animal", animal, _ANIMAL_FIELDS + ["status", "disabled"], as_dict=True)
	if not row or row.disabled or row.status in RETIRED_STATUSES:
		return None
	# last_weight_kg is a snapshot the weight record leaves alone when its last
	# record is cancelled; a weight no submitted record carries is not evidence.
	if not frappe.db.exists("Livestock Weight Record", {"animal": animal, "docstatus": 1}):
		return None
	return _check(row, _classes(), fattening_bands())


def band_suggestions():
	"""band_check over every candidate: active animals in Fattening herds."""
	classes = _classes()
	bands = fattening_bands()
	if not classes or not bands:
		return []
	rows = frappe.get_all(
		"Animal",
		filters=[
			["current_herd", "in", list(classes)],
			["status", "not in", list(RETIRED_STATUSES)],
			["disabled", "=", 0],
			["last_weight_kg", ">", 0],
		],
		fields=_ANIMAL_FIELDS,
		limit=5000,
	)
	weighed = set(frappe.get_all(
		"Livestock Weight Record", filters={"docstatus": 1, "animal": ["in", [r.name for r in rows] or [""]]},
		pluck="animal"))
	out = [c for c in (_check(r, classes, bands) for r in rows if r.name in weighed) if c]
	out.sort(key=lambda c: (c["kind"], c["herd"], c["label"]))
	return out
