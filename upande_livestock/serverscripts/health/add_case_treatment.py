"""Add a treatment to an open health case, issuing the drugs it consumes."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


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

		before = {t.name for t in doc.treatments or []}
		for t in treatments:
			doc.append(
				"treatments",
				{
					"treatment_date": t.get("treatment_date") or d.get("treatment_date") or today(),
					"drug_item": t.get("drug_item") or None,
					"drug_name_text": t.get("drug_name_text"),
					"dosage": t.get("dosage"),
					"qty": flt(t.get("qty")) or 1,
					"route": t.get("route") or None,
					"withdrawal_period_days": int(flt(t.get("withdrawal_period_days"))) or None,
					"administered_by": t.get("administered_by") or current_employee(),
					"notes": t.get("notes"),
				},
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
