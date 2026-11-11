# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""When a birth may be recorded, and who may back-record what it needs.

THE RULE THE FARM AGREED. A calf comes from a pregnancy, and a pregnancy from a
service. A birth is recorded straight away when the dam has

1. a confirmed pregnancy diagnosis not yet closed by a calving or an abortion, or
2. a service, not yet calved from, whose date puts the birth inside
   [service + minimum, service + maximum] days (Livestock Settings → Birth
   Window, 270–295 for cattle).

Anything else is a birth with no recorded cause, and the record is refused —
not quietly patched with a service the system invented, which is what the
calving once did on a natural-service farm. The missing records are instead
written by a person, backdated, through the RETRO PATH: the service on the day
it happened, optionally its diagnosis, and the herd the dam was in that day,
then the birth — one request, all or nothing.

WHO MAY TAKE THE RETRO PATH. Back-recording a service rewrites a cow's history
nine months deep, and her herd history with it. A Livestock Manager may do it at
any time. Anyone else only while the farm's backdating window is open (Livestock
Settings → Backdating Open), which is the farm saying "history is being loaded
now". Closed, the refusal says who can.

Cattle only. Sheep and goats are kept by number (common/shoats) and have no
per-animal calving to guard.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common.timings import get_timing

MANAGER_ROLE = "Livestock Manager"

#: The `code` a refused birth carries in its answer, so a client can offer the
#: retro path instead of only showing the words.
NEEDS_SERVICE = "birth_needs_service"


class BirthNeedsService(frappe.ValidationError):
	"""A birth with no confirmed pregnancy and no service in the window.

	Carries `code` and `details` so `envelope.run` can hand a client what it
	needs to offer the retro path (the window, the dates a service may take,
	whether this user may take it) rather than only the sentence.
	"""

	code = NEEDS_SERVICE

	def __init__(self, message, details=None):
		super().__init__(message)
		self.details = details or {}


def window():
	"""(minimum, maximum) gestation days a birth must fall within after its service."""
	low = get_timing("gestation_window_min_days")
	high = get_timing("gestation_window_max_days")
	if high < low:
		low, high = high, low
	return low, high


def service_dates_for(birth_date):
	"""(earliest, latest) service date that puts `birth_date` inside the window."""
	low, high = window()
	birth = getdate(birth_date)
	return getdate(add_days(birth, -high)), getdate(add_days(birth, -low))


def fits(service_date, birth_date):
	"""Does a service on `service_date` put a birth on `birth_date` inside the window?"""
	if not service_date or not birth_date:
		return False
	earliest, latest = service_dates_for(birth_date)
	return earliest <= getdate(service_date) <= latest


def _open_services(dam, birth_date):
	"""Submitted services on `dam` on or before the birth, newest first, that no
	calving or abortion has closed (none on or after the service date)."""
	return frappe.db.sql(
		"""SELECT s.name, s.service_date, s.service_type, s.pregnancy_confirmation_status,
		          IFNULL(s.custom_is_backdated, 0) AS is_backdated
		   FROM `tabLivestock Event` s
		   WHERE s.animal = %(dam)s AND s.event_type = 'Service' AND s.docstatus = 1
		     AND s.service_date <= %(birth)s
		     AND IFNULL(s.pregnancy_confirmation_status, 'Pending') IN ('Pending', 'Confirmed')
		     AND NOT EXISTS (
		       SELECT 1 FROM `tabLivestock Event` c
		       WHERE c.animal = s.animal AND c.docstatus = 1
		         AND c.event_type IN ('Calving', 'Abortion')
		         AND (c.custom_related_pregnancy = s.name OR c.event_date >= s.service_date))
		   ORDER BY s.service_date DESC, s.creation DESC""",
		{"dam": dam, "birth": str(getdate(birth_date))},
		as_dict=True,
	)


def basis(dam, birth_date):
	"""What lets a birth on `birth_date` be recorded for `dam`, or None.

	{"kind": "diagnosis"|"service", "service": name, "service_date": date}. A
	confirmed pregnancy wins over an unconfirmed service in the window: the vet
	said she was carrying, and the calf is the end of that pregnancy.
	"""
	services = _open_services(dam, birth_date)
	for s in services:
		if s.pregnancy_confirmation_status == "Confirmed":
			return {"kind": "diagnosis", "service": s.name, "service_date": str(s.service_date)}
	for s in services:
		if fits(s.service_date, birth_date):
			return {"kind": "service", "service": s.name, "service_date": str(s.service_date)}
	return None


def accepts(dam, birth_date, service):
	"""Is `service` one this birth may be recorded against (confirmed, or in the window)?"""
	return any(
		s.name == service and (s.pregnancy_confirmation_status == "Confirmed" or fits(s.service_date, birth_date))
		for s in _open_services(dam, birth_date)
	)


def is_manager():
	roles = set(frappe.get_roles())
	return bool(roles & {MANAGER_ROLE, "System Manager", "Administrator"})


def retro_refusal():
	"""Why this user may not take the retro path now, or None if they may."""
	if is_manager() or backdate.window_open():
		return None
	return _(
		"Back-recording a service is for a Livestock Manager while backdating is closed. "
		"Ask a manager to record this birth, or to turn on Backdating Open in Livestock Settings."
	)


def allows_diagnosis():
	"""Livestock Settings → Allow pregnancy diagnosis when back-recording a service."""
	raw = frappe.db.get_single_value("Livestock Settings", "allow_retro_pregnancy_diagnosis")
	return True if raw is None else bool(cint(raw))


def details(dam, birth_date):
	"""Everything a client needs to explain the rule and offer the retro path."""
	low, high = window()
	earliest, latest = service_dates_for(birth_date)
	refusal = retro_refusal()
	return {
		"dam": dam,
		"birth_date": str(getdate(birth_date)),
		"window": {"min_days": low, "max_days": high},
		"service_from": str(earliest),
		"service_to": str(latest),
		"retro_allowed": refusal is None,
		"retro_refusal": refusal or "",
		"is_manager": is_manager(),
		"backdating_open": backdate.window_open(),
		"allow_diagnosis": allows_diagnosis(),
	}


def refusal_message(dam, birth_date):
	low, high = window()
	earliest, latest = service_dates_for(birth_date)
	return _(
		"{0} has no confirmed pregnancy and no service that fits a birth on {1}. "
		"A calf is born {2}–{3} days after its service, so the service would have been "
		"between {4} and {5}. Record that service first (backdated), then the birth."
	).format(
		dam, frappe.utils.formatdate(birth_date), low, high,
		frappe.utils.formatdate(earliest), frappe.utils.formatdate(latest),
	)


def assert_birth_allowed(dam, birth_date):
	"""The basis for this birth, or raise BirthNeedsService with what to do instead."""
	found = basis(dam, birth_date)
	if found:
		return found
	raise BirthNeedsService(refusal_message(dam, birth_date), details(dam, birth_date))
