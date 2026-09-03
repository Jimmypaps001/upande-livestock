"""Record an animal's weight."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common.company import company_or_throw
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


@frappe.whitelist()
def create_weight_record(payload):
	"""Record a weighing as a Livestock Weight Record.

	The doctype owns the derived columns (previous weight, daily gain) and the
	minimum-interval guard, so this endpoint only carries the measurement across.
	"""

	def go():
		guard("Livestock Weight Record")
		d = as_dict(payload)
		if not d.get("animal"):
			frappe.throw(_("Select an animal."))
		weight = flt(d.get("weight_kg"))
		if weight <= 0:
			frappe.throw(_("Weight must be greater than zero."))
		doc = frappe.new_doc("Livestock Weight Record")
		doc.animal = d.get("animal")
		doc.company = company_or_throw(d.get("company"))
		doc.weight_date = d.get("weight_date") or today()
		doc.measured_by = d.get("measured_by") or current_employee()
		doc.method = d.get("method") or None
		doc.weight_kg = weight
		doc.bcs = flt(d.get("bcs")) or None
		doc.heart_girth_cm = flt(d.get("heart_girth_cm")) or None
		doc.remarks = d.get("remarks")
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True,
			"name": doc.name,
			"weight_kg": doc.weight_kg,
			"daily_gain_kg": doc.daily_gain_kg,
			"previous_weight_kg": doc.previous_weight_kg,
		}

	return run(go, "livestock create_weight_record failed")
