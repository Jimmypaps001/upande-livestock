"""The one place every write endpoint builds a Livestock Event.

Movement, Heat Detection, Drying Off, Service, Pregnancy Diagnosis and
Abortion are all the same doctype with a different `event_type`, so
`new_livestock_event` is what keeps their common fields — the operator, the
canonical `event_date` — from being set five slightly different ways.
"""

import frappe

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common.employee import employee_or_throw


def new_livestock_event(d, event_type, date_key=None):
	"""Build an unsaved Livestock Event of `event_type`.

	`event_date` is the canonical date for every event type: livestock_guards.py
	keys its age and interval rules on it, and the desk form relabels it per type
	("Service Date", "Movement Date", "Diagnosis Date"). A form that collects only
	the type-specific date therefore passes `date_key` so that date also becomes
	`event_date`. Without it a backdated entry stored the right `service_date` and
	an `event_date` of today, leaving the two out of step and the interval guards
	reading the wrong day.

	The same date decides whether this is a historical record. `backdate.resolve`
	uses exactly the precedence above, so the date the event carries and the date
	it is judged by are the same date by construction rather than by agreement.
	"""
	event_date, is_backdated = backdate.resolve(d, date_key)
	backdate.assert_allowed(is_backdated)

	doc = frappe.new_doc("Livestock Event")
	doc.animal = d.get("animal")
	doc.event_type = event_type
	doc.event_date = event_date
	doc.operator = employee_or_throw(d.get("operator"))
	doc.remarks = d.get("remarks")
	backdate.stamp(doc, is_backdated)
	return doc
