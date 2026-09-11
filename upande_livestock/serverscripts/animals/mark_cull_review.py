# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Mark a cow for cull review, or take the mark off again."""

import frappe
from frappe import _
from frappe.utils import today

from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, run


@frappe.whitelist()
def mark_cull_review(payload):
	"""Record that somebody thinks this cow should go, and why.

	A JUDGEMENT, NOT A DISPOSAL. She keeps her herd, her place in the head count
	and her ration; nothing about the farm's arithmetic changes. Culling her is
	a Livestock Disposal, which is a different act with a different permission
	and an accounting consequence — this only says a person looked at her
	figures and thought it worth raising.

	The reason is stored as given rather than recomputed later. It is the case
	that was made on the day, against the herd as it stood then; a cow marked
	when she was bottom of the herd should not quietly stop being marked because
	two worse cows were bought in.

	It also writes a Livestock Event, so the mark appears in her timeline beside
	everything else that happened to her, with a date and a name against it.
	"""

	def go():
		if not frappe.has_permission("Animal", "write"):
			frappe.throw(_("You are not permitted to mark animals for review."),
			             frappe.PermissionError)

		d = as_dict(payload)
		name = (d.get("animal") or "").strip()
		if not name:
			frappe.throw(_("Select the animal."))
		if not frappe.db.exists("Animal", name):
			frappe.throw(_("{0} is not an animal on this farm.").format(name))

		marked = bool(d.get("marked", True))
		reason = (d.get("reason") or "").strip()
		if marked and not reason:
			frappe.throw(
				_("Say why she is being marked. A mark with no case behind it is one "
				  "nobody can review.")
			)

		doc = frappe.get_doc("Animal", name)
		doc.db_set({
			"custom_cull_candidate": 1 if marked else 0,
			"custom_cull_reason": reason if marked else None,
			"custom_cull_marked_on": today() if marked else None,
			"custom_cull_marked_by": frappe.session.user if marked else None,
		}, update_modified=False)

		_write_event(doc, marked, reason)

		return {
			"ok": True,
			"animal": name,
			"marked": marked,
			"reason": reason if marked else "",
			"on": today() if marked else None,
		}

	return run(go, "livestock mark_cull_review failed")


def _write_event(animal, marked, reason):
	"""Put the decision in her history.

	Best effort: the mark itself is the thing that matters, and a site whose
	Livestock Event Type list has not been extended should not lose the mark
	because the timeline entry would not insert.
	"""
	try:
		event = frappe.new_doc("Livestock Event")
		event.event_type = "Check Up"
		event.animal = animal.name
		event.event_date = today()
		event.current_herd = animal.current_herd or ""
		event.operator = current_employee()
		event.remarks = (
			"Marked for cull review — {}".format(reason)
			if marked
			else "Cull review mark removed"
		)
		event.insert(ignore_permissions=True)
		event.submit()
	except Exception:
		frappe.clear_last_message()
