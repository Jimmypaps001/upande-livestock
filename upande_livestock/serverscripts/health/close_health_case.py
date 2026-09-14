# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Close a health case: how it ended, and on what day."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.health_case import CLOSED_STATUSES, TREATING_STATUSES


@frappe.whitelist()
def close_health_case(payload):
	"""Write the ending on a file and shut it.

	NOTHING COULD CLOSE A CASE BEFORE. `case_status`, `closed_date` and every
	outcome field were sealed on submit, so a farm could open files and never
	shut one — which is why this site has cows carrying three open cases at once
	and an open-case count that means nothing. The outcome fields are what a
	case LEARNS after it is opened, and they are writable now; the front of the
	file — the animal, the day, the complaint it was opened on — is not, because
	that is the record of what was thought at the time.

	HOW IT ENDED IS NOT OPTIONAL. A file shut with no ending is the same as a
	file left open, except it stops being counted. Recovered, Chronic, Died and
	Culled are the four the doctype has and one of them has to be chosen.

	Died or Culled here does NOT dispose of the animal. That is a Livestock
	Disposal, with a vet and a manager behind it — this only records how the
	illness ended. Saying otherwise would let a health screen retire a cow.
	"""

	def go():
		guard("Livestock Health Case")
		d = as_dict(payload)
		name = (d.get("case") or "").strip()
		if not name:
			frappe.throw(_("Select a case."))
		if not frappe.db.exists("Livestock Health Case", name):
			frappe.throw(_("There is no case called {0}.").format(name))

		doc = frappe.get_doc("Livestock Health Case", name)
		if doc.docstatus != 1:
			frappe.throw(_("Case {0} is not submitted.").format(name))
		if doc.case_status not in TREATING_STATUSES:
			frappe.throw(
				_("Case {0} is already closed — it ended as {1}.").format(name, doc.case_status)
			)

		outcome = (d.get("case_status") or "").strip()
		if outcome not in CLOSED_STATUSES:
			frappe.throw(
				_("Say how it ended: {0}.").format(", ".join(CLOSED_STATUSES))
			)

		closed_on, is_backdated = backdate.resolve(
			{"event_date": d.get("closed_date")}, "closed_date"
		)
		backdate.assert_allowed(is_backdated)
		if doc.opened_date and getdate(closed_on) < getdate(doc.opened_date):
			frappe.throw(
				_("She cannot have recovered before the file was opened on {0}.").format(
					doc.opened_date
				)
			)

		doc.case_status = outcome
		doc.closed_date = closed_on
		doc.duration_days = (
			date_diff(getdate(closed_on), getdate(doc.opened_date)) if doc.opened_date else None
		)
		if d.get("outcome_notes"):
			doc.outcome_notes = d["outcome_notes"]
		if d.get("confirmed_diagnosis"):
			doc.confirmed_diagnosis = d["confirmed_diagnosis"]
		if d.get("production_loss_kg") is not None:
			doc.production_loss_kg = flt(d["production_loss_kg"])
		doc.flags.ignore_permissions = True
		doc.save()
		doc.reload()

		return {
			"ok": True,
			"case": doc.name,
			"animal": doc.animal,
			"case_status": doc.case_status,
			"closed_date": str(doc.closed_date),
			"duration_days": doc.duration_days,
		}

	return run(go, "livestock close_health_case failed")
