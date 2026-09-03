# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Keep a Livestock Event row in step with a health detail document.

Livestock Event is the animal's timeline; Livestock Diagnosis and Livestock
Health Case hold the clinical detail. Each detail document owns exactly one
event, pointing back at it through reference_doctype / reference_name, so one
list shows an animal's whole history without clinical fields leaking onto it.
"""

import frappe


def _existing_event(doc):
	return frappe.db.get_value(
		"Livestock Event",
		{"reference_doctype": doc.doctype, "reference_name": doc.name, "docstatus": ["<", 2]},
		"name",
	)


def _event_date_of(doc):
	for fieldname in ("diagnosis_date", "opened_date", "event_date"):
		if doc.meta.has_field(fieldname) and doc.get(fieldname):
			return doc.get(fieldname)
	return frappe.utils.today()


def sync_event_for(doc, event_type):
	"""Create or update this document's Livestock Event. Returns the event name.

	Idempotent — calling it twice for the same document updates the same event
	rather than creating a second one.
	"""
	event_date = _event_date_of(doc)
	operator = doc.get("operator") or doc.get("opened_by")

	name = _existing_event(doc)
	if name:
		event = frappe.get_doc("Livestock Event", name)
		event.db_set("event_date", event_date, update_modified=False)
		return event.name

	event = frappe.new_doc("Livestock Event")
	event.animal = doc.animal
	event.event_type = event_type
	event.event_date = event_date
	event.reference_doctype = doc.doctype
	event.reference_name = doc.name
	if operator:
		event.operator = operator
	if doc.meta.has_field("current_herd") and doc.get("current_herd"):
		event.current_herd = doc.current_herd
	event.remarks = f"Auto-created from {doc.doctype} {doc.name}"
	event.flags.ignore_permissions = True
	event.insert(ignore_permissions=True)
	event.submit()
	return event.name


def cancel_event_for(doc):
	"""Cancel this document's Livestock Event, if it has a live one."""
	name = _existing_event(doc)
	if not name:
		return
	event = frappe.get_doc("Livestock Event", name)
	if event.docstatus == 1:
		event.flags.ignore_permissions = True
		event.cancel()
