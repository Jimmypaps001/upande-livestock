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


# --- undoing what an event stamped ------------------------------------------
#
# A Service marks the cow Served, a diagnosis marks her Pregnant, a calving sets
# her calving date and parity, a selection move sets the bull's stream and note.
# Cancelling (or force-deleting) the event used to leave all of it behind, so a
# cow stayed "Served" with the date of a service that never was. The animal's
# breeding state is therefore RE-DERIVED from the events that are still
# standing, which is correct for any order of undoing.

DERIVED_REMARK = "Derived from the calving"


def _has(doctype, field):
	return frappe.get_meta(doctype).has_field(field)


def restore_breeding_state(animal, exclude=None):
	"""Set the animal's service/pregnancy/calving stamps from its standing events."""
	if not animal or not frappe.db.exists("Animal", animal):
		return
	base = {"animal": animal, "docstatus": 1}
	if exclude:
		base["name"] = ["!=", exclude]
	services = frappe.get_all(
		"Livestock Event", filters={**base, "event_type": "Service"},
		fields=["name", "service_date", "pregnancy_confirmation_status", "expected_calving_date"],
		order_by="service_date desc, creation desc")
	calvings = frappe.get_all(
		"Livestock Event", filters={**base, "event_type": ["in", ["Calving", "Abortion"]]},
		fields=["name", "event_type", "event_date"], order_by="event_date desc")
	closed_after = lambda day: any(getdate(c.event_date) >= getdate(day) for c in calvings)  # noqa: E731
	carrying = next((s for s in services if s.pregnancy_confirmation_status == "Confirmed"
	                 and not closed_after(s.service_date)), None)
	pending = next((s for s in services if s.pregnancy_confirmation_status == "Pending"), None)
	births = [c for c in calvings if c.event_type == "Calving"]

	values = {
		"last_service_date": services[0].service_date if services else None,
		"last_calving_date": births[0].event_date if births else None,
		"expected_calving_date": carrying.expected_calving_date if carrying else None,
	}
	if carrying:
		repro, preg = "Pregnant", "Confirmed"
	elif pending:
		repro, preg = "Served", "Pending Check"
	else:
		dob = frappe.db.get_value("Animal", animal, "date_of_birth")
		young = dob and (getdate(frappe.utils.today()) - getdate(dob)).days < 24 * 30
		repro = "Open" if births or not young else "Heifer"
		preg = "Not Pregnant"
	values["repro_status"] = repro
	if _has("Animal", "custom_pregnancy_status"):
		values["custom_pregnancy_status"] = preg
	frappe.db.set_value("Animal", animal, values, update_modified=False)


def recompute_stream(animal, exclude=None):
	"""A bull's stream and breeding note, from the moves still standing."""
	row = frappe.db.get_value("Animal", animal, ["sex", "date_of_birth"], as_dict=True)
	if not row or row.sex != "Male":
		return
	filters = {"animal": animal, "event_type": "Movement", "docstatus": 1}
	if exclude:
		filters["name"] = ["!=", exclude]
	stream, note = "", None
	for m in frappe.get_all("Livestock Event", filters=filters, order_by="event_date asc, creation asc",
	                        fields=["current_herd", "new_herd", "remarks", "operator", "event_date"]):
		cls = herd_class(m.new_herd)
		if cls == "Fattening":
			stream = "Feedlot"
		elif cls == "Breeding":
			young = row.date_of_birth and add_months(
				getdate(row.date_of_birth), get_timing("breeding_bull_min_age_months")) > getdate(m.event_date)
			if herd_class(m.current_herd) != "Breeding" or (stream != "Breeding" and young):
				stream = "Breeding"
				note = {"breeding_note": (m.remarks or "").strip(), "breeding_note_by": m.operator,
				        "breeding_note_on": m.event_date}
	values = {"stream": stream, "breeding_note": None, "breeding_note_by": None, "breeding_note_on": None}
	if stream == "Breeding" and note:
		values.update(note)
	frappe.db.set_value("Animal", animal, values, update_modified=False)


def _cancel_todos(doc_name):
	for todo in frappe.get_all("ToDo", filters={"reference_type": "Livestock Event", "reference_name": doc_name,
	                                           "status": ["!=", "Cancelled"]}, pluck="name"):
		frappe.db.set_value("ToDo", todo, "status", "Cancelled", update_modified=False)


def undo_event(doc):
	"""Take back what a submitted event stamped (called as it is cancelled).

	A submitted event cannot be deleted in Frappe, so cancelling is the only way
	out, and a cancelled event is deleted afterwards with nothing left to undo."""
	exclude = None
	kind = doc.event_type
	if kind == "Service":
		_cancel_todos(doc.name)
		restore_breeding_state(doc.animal, exclude)
	elif kind == "Pregnancy Diagnosis":
		if doc.related_service and not frappe.db.exists("Livestock Event", {
			"event_type": "Pregnancy Diagnosis", "related_service": doc.related_service, "docstatus": 1,
			"name": ["!=", doc.name]}):
			frappe.db.set_value("Livestock Event", doc.related_service, {
				"pregnancy_confirmation_status": "Pending", "pregnancy_confirmation_date": None},
				update_modified=False)
		restore_breeding_state(doc.animal, exclude)
	elif kind == "Calving":
		_undo_calving(doc, exclude)
	elif kind == "Birth":
		_undo_birth(doc)
	elif kind == "Movement":
		recompute_stream(doc.animal, exclude)


def _cancel(name):
	child = frappe.get_doc("Livestock Event", name)
	if child.docstatus == 1:
		child.cancel()


def _undo_calving(doc, exclude):
	for birth in frappe.get_all("Livestock Event", filters={
		"event_type": "Birth", "related_calving": doc.name, "docstatus": 1}, pluck="name"):
		_cancel(birth)
	# the move that put the dam in the cow herd after this calving
	for move in frappe.get_all("Livestock Event", filters={
		"event_type": "Movement", "animal": doc.animal, "docstatus": 1,
		"remarks": ["like", "Calved on%{0}".format(doc.name)]}, pluck="name"):
		_cancel(move)
	# a pregnancy this calving derived (no service was on file) goes with it
	service = doc.custom_related_pregnancy
	if service and (frappe.db.get_value("Livestock Event", service, "remarks") or "").startswith(DERIVED_REMARK):
		for dx in frappe.get_all("Livestock Event", filters={
			"event_type": "Pregnancy Diagnosis", "related_service": service, "docstatus": 1}, pluck="name"):
			_cancel(dx)
		_cancel(service)
	parity = frappe.db.get_value("Animal", doc.animal, "parity")
	if parity:
		frappe.db.set_value("Animal", doc.animal, "parity", max(0, int(parity) - 1), update_modified=False)
	restore_breeding_state(doc.animal, exclude)


def _undo_birth(doc):
	"""A calf with nothing else recorded goes with its Birth; one with a history is left, disabled."""
	calf = doc.animal
	if not calf or not frappe.db.exists("Animal", calf):
		return
	others = frappe.db.exists("Livestock Event", {"animal": calf, "docstatus": 1, "name": ["!=", doc.name]}) \
		or frappe.db.exists("Livestock Weight Record", {"animal": calf, "docstatus": 1})
	herd = frappe.db.get_value("Animal", calf, "current_herd")
	if others:
		frappe.db.set_value("Animal", calf, {"disabled": 1, "status": "Transferred Out"}, update_modified=False)
	else:
		frappe.db.sql("delete from `tabLivestock Alert` where animal = %s", calf)
		frappe.delete_doc("Animal", calf, force=True, ignore_permissions=True)
	from upande_livestock.serverscripts.common.animal import recompute_herd_count

	recompute_herd_count(herd)
