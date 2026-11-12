# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which events this farm records at all.

Not every farm does every event: for some, a pregnancy diagnosis is not a must,
and a PD form, a "PD due" alert and a pregnancy-check row on the breeding list
are noise they learn to skip. So each Livestock Event Type has an Enabled
switch — its `is_active` box, relabelled, because that box already meant "this
type is in use" (the bootstrap and the Stock tab listed only active types) and
changed nothing else; a second switch beside it would be two answers to one
question.

An event switched off disappears everywhere it would be offered: the web and
phone menus, the alerts and worklists that would prompt for it, the retro birth
path's optional diagnosis step — and the server refuses to record one, so a
stale phone or a hand-made request cannot slip one in. Events already on record
stay; switching an event back on brings everything back.

Read once per request (`frappe.local` cache): the alert sweeps and the
controller ask for every row they look at.
"""

import frappe
from frappe import _

EVENT_TYPE = "Livestock Event Type"

#: Alert kinds that exist only to prompt for one event type. With that event
#: switched off the alert is not raised, and one already open is settled.
#: Kinds about the animal rather than an event (an open cow, a weight band, the
#: store running low) are not here: they stay whatever is switched off.
ALERT_EVENT = {
	"Pregnancy Check Overdue": "Pregnancy Diagnosis",
	"Calving Due": "Calving",
	"Weighing Overdue": "Weight Recording",
	"Move Due": "Movement",
	"Move Overdue": "Movement",
}


def _disabled():
	cache = getattr(frappe.local, "livestock_disabled_events", None)
	if cache is not None:
		return cache
	try:
		cache = frozenset(frappe.get_all(EVENT_TYPE, filters={"is_active": 0}, pluck="name"))
	except Exception:
		# A site mid-install without the table records nothing anyway; refusing
		# every event for it would be the wrong failure.
		cache = frozenset()
	frappe.local.livestock_disabled_events = cache
	return cache


def forget():
	"""Drop this request's cached answer (an event type was just saved)."""
	frappe.local.livestock_disabled_events = None


def disabled_events():
	"""The event types switched off, sorted."""
	return sorted(_disabled())


def is_enabled(event_type):
	"""Is `event_type` recorded on this farm? An unknown or blank type is not
	ours to refuse here — the Link validation says what is wrong with it."""
	return not event_type or event_type not in _disabled()


def refusal(event_type):
	"""The words a refused record carries."""
	return _("{0} is switched off for this farm, so it cannot be recorded. "
	         "A Livestock Manager can switch it on in Settings → Events.").format(_(event_type))


def assert_enabled(event_type):
	"""Refuse to record an event of a type the farm switched off."""
	if not is_enabled(event_type):
		frappe.throw(refusal(event_type), title=_("Event switched off"))


def alert_wanted(kind):
	"""Should an alert of `kind` be raised? Not when it prompts for an event that is off."""
	event_type = ALERT_EVENT.get(kind)
	return not event_type or is_enabled(event_type)
