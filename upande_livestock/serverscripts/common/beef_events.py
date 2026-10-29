# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Beef rules the Livestock Event controller applies: selection moves, inbreeding
warnings on a move, and the sire of a service.

Called from LivestockEvent.validate / on_submit so every write path (desk form,
`create_movement_event`, `move_animals`, the phone's `record_animal_event`)
gets them. Nothing here blocks except the one missing field a selection move
needs: the herdsman's note.
"""

import frappe
from frappe import _
from frappe.utils import add_months, getdate

from upande_livestock.serverscripts.common import kinship, warnings
from upande_livestock.serverscripts.common.beef_settings import default_service_type, kinship_check_on
from upande_livestock.serverscripts.common.timings import get_timing

MIN_NOTE_CHARS = 20


def herd_class(herd):
	return frappe.db.get_value("Herds", herd, "herd_class") if herd else None


def herd_label(herd):
	return frappe.db.get_value("Herds", herd, "herd_name") or herd


def _stream_of(animal):
	return frappe.db.get_value("Animal", animal, "stream")


def is_selection(animal, from_herd, to_herd, on=None):
	"""Is this move the decision to keep a bull for breeding?

	A male into a Breeding-class herd from a herd that is not one (calf group,
	feedlot, holding pen). A calf that lives in its dam's Breeding herd leaves it
	for the Bull Reserve from a Breeding herd, so a young male not yet in the
	breeding stream counts too; a mature bull rotating between mating groups does
	not.
	"""
	if herd_class(to_herd) != "Breeding":
		return False
	row = frappe.db.get_value("Animal", animal, ["sex", "stream", "date_of_birth"], as_dict=True)
	if not row or row.sex != "Male":
		return False
	if herd_class(from_herd) != "Breeding":
		return True
	if row.stream == "Breeding":
		return False
	if not row.date_of_birth:
		return False
	mature = add_months(getdate(row.date_of_birth), get_timing("breeding_bull_min_age_months"))
	return mature > getdate(on or frappe.utils.today())


def warnings_for_move(animal, new_herd, on=None):
	"""Inbreeding sentences for putting `animal` into `new_herd`; [] unless it is a mating group."""
	if not kinship_check_on() or herd_class(new_herd) != "Breeding":
		return []
	return [
		_("Inbreeding risk in {0}: {1}").format(herd_label(new_herd), c["message"])
		for c in kinship.conflicts(animal, new_herd, on=on)
	]


def check_movement(doc):
	"""Livestock Event.validate for a Movement, before the herd is changed."""
	if doc.event_type != "Movement" or not doc.animal or not doc.new_herd:
		return
	if is_selection(doc.animal, doc.current_herd, doc.new_herd, doc.event_date):
		note = (doc.remarks or "").strip()
		if len(note) < MIN_NOTE_CHARS:
			frappe.throw(
				_("Describe the bull and why he is kept for breeding (at least {0} characters).").format(
					MIN_NOTE_CHARS),
				frappe.MandatoryError,
			)
	found = warnings_for_move(doc.animal, doc.new_herd, doc.event_date)
	doc.kinship_warnings = "\n".join(found) if found else None
	for sentence in found:
		warnings.note(sentence)
		frappe.msgprint(sentence, alert=True, indicator="orange")


def after_movement(doc):
	"""Livestock Event.on_submit for a Movement: the stream the move decided."""
	if doc.event_type != "Movement" or not doc.animal or not doc.new_herd:
		return
	cls = herd_class(doc.new_herd)
	if frappe.db.get_value("Animal", doc.animal, "sex") != "Male":
		return
	if cls == "Fattening":
		frappe.db.set_value("Animal", doc.animal, "stream", "Feedlot", update_modified=False)
	elif cls == "Breeding" and is_selection(doc.animal, doc.current_herd, doc.new_herd, doc.event_date):
		frappe.db.set_value("Animal", doc.animal, {
			"stream": "Breeding",
			"breeding_note": (doc.remarks or "").strip(),
			"breeding_note_by": doc.operator,
			"breeding_note_on": doc.event_date,
		}, update_modified=False)


# --- Service --------------------------------------------------------------


def settle_service_type(doc):
	if not doc.service_type:
		doc.service_type = default_service_type()


def settle_service_sire(doc):
	"""Livestock Event.validate for a Service: conception date, sire, kinship.

	A sire somebody chose (`sire_animal`) or typed (`sire`, an A.I. straw or an
	outside bull) is never second-guessed. For a natural service with neither,
	the sire is the mature bull who was in her herd around conception; several
	bulls leave it blank and `flags.sire_inference` carries the candidates.
	"""
	from upande_livestock.serverscripts.common import sire_inference

	natural = (doc.service_type or "").lower().startswith("natural")
	if natural and not doc.conception_date:
		doc.conception_date = doc.service_date

	if doc.sire_animal:
		bull = frappe.db.get_value("Animal", doc.sire_animal, ["sex", "tag_number", "burn_name"], as_dict=True)
		if not bull or bull.sex != "Male":
			frappe.throw(_("{0} is not a bull on this farm.").format(doc.sire_animal))
		if not doc.sire_inferred:
			doc.sire_basis = None
		if not (doc.sire or "").strip():
			doc.sire = bull.tag_number or bull.burn_name or doc.sire_animal
	elif natural and not (doc.sire or "").strip() and not doc.flags.sire_unknown:
		got = sire_inference.infer_sire(doc.animal, doc.conception_date or doc.service_date)
		doc.flags.sire_inference = got
		if got["inferred"]:
			doc.sire_animal = got["sire"]
			doc.sire_inferred = 1
			doc.sire_basis = got["basis"]
			doc.sire = got["candidates"][0]["label"]

	if doc.sire_animal and kinship_check_on():
		found = kinship.relation(doc.sire_animal, doc.animal)
		if found:
			sentence = _("Inbreeding risk: {0}").format(found["message"])
			doc.kinship_warnings = sentence
			warnings.note(sentence)
			frappe.msgprint(sentence, alert=True, indicator="orange")
		else:
			doc.kinship_warnings = None
