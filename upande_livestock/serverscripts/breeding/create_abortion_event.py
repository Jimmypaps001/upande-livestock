"""Record a pregnancy loss.

An Abortion ends a pregnancy exactly as a Calving does, so the cow can be
re-served once the configured post-abortion window has passed."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event


@frappe.whitelist()
def create_abortion_event(payload):
	"""Record an Abortion as a first-class Livestock Event.

	`abortion_cause` is enforced by LivestockEvent.validate() rather than by a
	reqd flag on the field (mandatory_depends_on is browser-only in Frappe 16), so
	it is checked here too — otherwise the failure surfaces as a validation throw
	from deep in the controller instead of a clean message on the form.

	The pregnancy link is deliberately not required: the controller auto-links the
	animal's open Confirmed pregnancy when `custom_related_pregnancy` is blank, and
	an abortion with no pregnancy on file is legitimate data rather than an error.
	"""

	def go():
		guard("Livestock Event")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		if not d.get("abortion_cause"):
			frappe.throw(_("Select the cause of abortion."))
		doc = new_livestock_event(d, "Abortion")
		doc.abortion_cause = d.get("abortion_cause")
		doc.abortion_notes = d.get("abortion_notes")
		if d.get("related_pregnancy"):
			doc.custom_related_pregnancy = d.get("related_pregnancy")
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"related_pregnancy": doc.custom_related_pregnancy or "",
			"ready_for_service_date": str(doc.ready_for_service_date or ""),
		}

	return run(go, "livestock create_abortion_event failed")
