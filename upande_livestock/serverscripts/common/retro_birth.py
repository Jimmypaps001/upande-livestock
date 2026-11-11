# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The retro path: back-record what a birth needs, then the birth.

A birth whose dam has no confirmed pregnancy and no service in the birth window
is refused (common/birth_window). The person recording it then says what
happened nine months ago, and this writes it, backdated and flagged:

1. the MOVEMENT — the herd she was in on the service date, as a Movement on that
   day, so her herd history (common/herd_history) and everything read from it
   (the sire a natural service infers, the feed history) see her there. The
   farm accepted that this rewrites feed history. It is history-only: she is
   not moved today. The move that follows in her history is corrected to have
   left that herd; with none, a closing move on the birth date takes her back
   to the herd she stands in now, so her history still ends where she is.
2. the SERVICE on the day it happened, its straw with it (a store short of the
   straw puts the issue down as a draft placeholder, common/stock);
3. optionally the PREGNANCY DIAGNOSIS that confirmed it, between the two dates,
   when Livestock Settings allows it;

and the caller then records the birth against that service. All in the one
request: `envelope.run` rolls the lot back if any step is refused.
"""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

from upande_livestock.serverscripts.common import backdate, birth_window, herd_history

RETRO_REMARK = "Back-recorded with the birth on {0}"


def check(dam, birth_date, retro):
	"""Refuse a retro request that breaks a rule, before anything is written."""
	refusal = birth_window.retro_refusal()
	if refusal:
		frappe.throw(refusal, frappe.PermissionError)
	found = birth_window.basis(dam, birth_date)
	if found:
		frappe.throw(
			_("{0} already has a {1} that covers a birth on {2} ({3}). Record the birth without back-recording a service.").format(
				dam,
				_("confirmed pregnancy") if found["kind"] == "diagnosis" else _("service"),
				formatdate(birth_date),
				found["service"],
			)
		)
	service_date = retro.get("service_date")
	if not service_date:
		frappe.throw(_("Give the date of the service this calf came from."))
	if not birth_window.fits(service_date, birth_date):
		low, high = birth_window.window()
		earliest, latest = birth_window.service_dates_for(birth_date)
		frappe.throw(
			_("A service on {0} does not fit a birth on {1}: a calf is born {2}–{3} days after its service, "
			  "so the service must be between {4} and {5}.").format(
				formatdate(service_date), formatdate(birth_date), low, high,
				formatdate(earliest), formatdate(latest))
		)
	herd = retro.get("herd")
	if not herd:
		frappe.throw(_("Choose the herd {0} was in on {1}.").format(dam, formatdate(service_date)))
	if not frappe.db.exists("Herds", herd):
		frappe.throw(_("{0} is not a herd on this farm.").format(herd))
	dx = retro.get("diagnosis") or None
	if dx:
		if not birth_window.allows_diagnosis():
			frappe.throw(_(
				"Livestock Settings does not allow a pregnancy diagnosis to be back-recorded with a service. "
				"Leave the diagnosis out."))
		dx_date = dx.get("diagnosis_date") or dx.get("event_date")
		if not dx_date or not (getdate(service_date) < getdate(dx_date) < getdate(birth_date)):
			frappe.throw(_("The pregnancy diagnosis must be dated after the service ({0}) and before the birth ({1}).").format(
				formatdate(service_date), formatdate(birth_date)))


def _move(dam, on, from_herd, to_herd, operator, remarks):
	"""A history-only Movement: read by her herd history, does not move her today."""
	move = frappe.new_doc("Livestock Event")
	move.event_type = "Movement"
	move.animal = dam
	move.event_date = str(getdate(on))
	move.current_herd = from_herd or ""
	move.new_herd = to_herd
	move.operator = operator
	move.remarks = remarks
	move.flags.history_only = True
	# `current_herd` fetches from the animal (where she stands TODAY) on every
	# save; here it is where she was that day, already checked (`check`).
	move.flags.ignore_links = True
	backdate.stamp(move, getdate(on) < getdate(today()))
	move.insert()
	move.submit()
	return move.name


def place_dam(dam, service_date, herd, birth_date, operator):
	"""Put her in `herd` on `service_date` in her herd history. Returns the moves made."""
	note = RETRO_REMARK.format(formatdate(birth_date))
	before = herd_history.herd_on(dam, service_date)
	if before == herd:
		return []
	made = [_move(dam, service_date, before, herd, operator, note)]
	later = frappe.get_all(
		"Livestock Event",
		filters={"animal": dam, "event_type": "Movement", "docstatus": 1,
		         "event_date": [">", str(getdate(service_date))], "name": ["not in", made]},
		fields=["name"], order_by="event_date asc, creation asc", limit=1)
	if later:
		# The next move in her history left the herd she was really in.
		frappe.db.set_value("Livestock Event", later[0].name, "current_herd", herd, update_modified=False)
		return made
	now = frappe.db.get_value("Animal", dam, "current_herd")
	if now and now != herd:
		# Nothing in her history takes her from `herd` to where she stands today;
		# the birth is the last day the record knows she was there.
		made.append(_move(dam, birth_date, herd, now, operator, note))
	return made


def record(dam, birth_date, retro, operator):
	"""Write the movement, service and (optional) diagnosis. Returns what was made."""
	from upande_livestock.serverscripts.breeding.create_pregnancy_diagnosis import build_diagnosis
	from upande_livestock.serverscripts.breeding.create_service_event import build_service

	check(dam, birth_date, retro)
	service_date = str(getdate(retro["service_date"]))
	note = RETRO_REMARK.format(formatdate(birth_date))
	moves = place_dam(dam, service_date, retro["herd"], birth_date, operator)

	fields = {k: retro.get(k) for k in (
		"service_type", "sire", "sire_animal", "sire_unknown", "conception_date",
		"items", "semen_item", "semen_qty", "semen_warehouse")}
	service = build_service(
		{**{k: v for k, v in fields.items() if v not in (None, "")}, "animal": dam,
		 "event_date": service_date, "operator": operator,
		 "remarks": "\n".join(x for x in (retro.get("remarks"), note) if x)},
		retro=True)

	diagnosis = None
	dx = retro.get("diagnosis") or None
	if dx:
		diagnosis = build_diagnosis(
			{"animal": dam, "event_date": str(getdate(dx.get("diagnosis_date") or dx.get("event_date"))),
			 "diagnosis_result": "Confirmed", "related_service": service.name, "operator": operator,
			 "vet": dx.get("vet"), "diagnosis_remarks": dx.get("diagnosis_remarks"), "remarks": note},
			retro=True)
	return {
		"service": service.name,
		"pregnancy_diagnosis": diagnosis.name if diagnosis else None,
		"movements": moves,
		"stock_entry": service.stock_entry or "",
	}
