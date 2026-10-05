"""Add a treatment to an open health case, issuing the drugs it consumes."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.health_case import TREATING_STATUSES, treatment_row


@frappe.whitelist()
def add_case_treatment(payload):
	"""Add today's treatment to an open case and issue its drugs.

	Treatments are `allow_on_submit`, and the issue guard lives on the row, so
	this appends to a live case rather than amending it. The drugs go out of the
	store as they are recorded — a case treated for five days posts five issues,
	not one, which is what the store actually saw.
	"""

	def go():
		guard("Livestock Health Case")
		d = as_dict(payload)
		if not d.get("case"):
			frappe.throw(_("Select a case."))
		treatments = [
			t for t in (d.get("treatments") or []) if t.get("drug_item") or t.get("drug_name_text")
		]
		if not treatments:
			frappe.throw(_("Add at least one treatment."))

		doc = frappe.get_doc("Livestock Health Case", d["case"])
		if doc.docstatus != 1:
			frappe.throw(_("Case {0} is not submitted.").format(doc.name))
		# As treat_animal refuses: a treatment on a Recovered or Died case is
		# a treatment on a file that has been closed.
		if doc.case_status not in TREATING_STATUSES:
			frappe.throw(_("Case {0} is {1}; open a new case to treat her again.").format(
				doc.name, doc.case_status))

		before = {t.name for t in doc.treatments or []}
		for t in treatments:
			# The shared builder, not a second copy of it. These two call sites
			# drifted: `treat_animal` carried the store and this one dropped it,
			# so where a drug came from depended on which door it came through.
			doc.append(
				"treatments",
				treatment_row(t, fallback_date=d.get("treatment_date")),
			)
		doc.flags.ignore_permissions = True
		doc.save()
		doc.reload()
		added = [t for t in doc.treatments or [] if t.name not in before]
		return {
			"ok": True,
			"name": doc.name,
			"animal": doc.animal,
			"added": len(added),
			"treatments": len(doc.treatments or []),
			"stock_entry": (added[0].stock_entry_ref if added else "") or "",
		}

	return run(go, "livestock add_case_treatment failed")
