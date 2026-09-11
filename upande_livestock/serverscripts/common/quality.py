# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where milk quality is recorded, and whether it has to be.

One module owns the answer so the milking form, the Quality page, the handset
and the tests cannot each decide it differently.

The distinction that matters: a lab figure is not a quantity. SCC, protein and
fat drive nothing — no stock moves, no money posts, no guard reads them. That
is exactly why they can be collected a day later from the creamery's docket
while `discarded_kg` and `price_per_kg` cannot: those two compute net yield and
revenue, which post a Stock Entry and a Journal Entry the moment the milking is
submitted.
"""

import frappe
from frappe.utils import flt

SETTINGS = "Livestock Settings"

#: The figures the creamery or the meter gives back. Nothing here posts.
LAB_FIELDS = ("bulk_scc", "fat_percent", "protein_percent")


def settings():
	return frappe.get_cached_doc(SETTINGS)


def capture_mode() -> str:
	"""'At milking' or 'Afterwards'. Defaults to at milking, which is what the
	farm did before this setting existed."""
	mode = (settings().get("custom_milk_quality_capture") or "").strip()
	return mode if mode in ("At milking", "Afterwards") else "At milking"


def captured_at_milking() -> bool:
	return capture_mode() == "At milking"


def required_at_milking() -> bool:
	"""Refuse a desk milking with no lab figures.

	Never consulted for the handset: a milker at the parlour cannot have a bulk
	tank SCC, and blocking them on one would stop the milking being recorded at
	all. See `stamp_pending`.
	"""
	return bool(settings().get("custom_quality_required_at_milking")) and captured_at_milking()


def required_in_lab() -> bool:
	return bool(settings().get("custom_quality_required_in_lab"))


def scc_ceiling() -> float:
	"""Above this a reading is worth saying something about. 0 turns it off."""
	return flt(settings().get("custom_quality_scc_ceiling"))


def has_readings(source) -> bool:
	"""True when any lab figure is present. Any, not all: a farm that only ever
	gets SCC back should not be chased forever for a fat percentage."""
	get = source.get if hasattr(source, "get") else (lambda k: getattr(source, k, None))
	return any(flt(get(f)) > 0 for f in LAB_FIELDS)


def is_outstanding(doc) -> bool:
	"""Whether this recording is still waiting on its lab figures.

	Three ways to be outstanding, and the third is the one that matters: a farm
	that requires quality AT MILKING still lets the handset through without it,
	because a milker at the parlour cannot have a bulk tank SCC. That recording
	has to be chased, or the requirement is enforced on the desk and silently
	waived for every phone on the farm.
	"""
	if has_readings(doc):
		return False
	return required_in_lab() or not captured_at_milking() or required_at_milking()


def stamp_pending(doc) -> None:
	"""Mark a recording as awaiting quality, or clear the mark.

	Written with db_set rather than on the in-memory document because this runs
	for submitted recordings too — the Quality page clearing the flag is the
	whole point of the field.
	"""
	if not doc.meta.has_field("custom_quality_pending"):
		return
	want = 1 if is_outstanding(doc) else 0
	if int(doc.get("custom_quality_pending") or 0) != want:
		doc.db_set("custom_quality_pending", want, update_modified=False)
