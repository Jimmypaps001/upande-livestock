"""Record an animal's weight."""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common import backdate
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
		return record_one(as_dict(payload))

	return run(go, "livestock create_weight_record failed")


def record_one(d):
	"""Write one weighing, throwing rather than answering with an envelope.

	SPLIT OUT SO A BATCH CAN SURVIVE A BAD ROW. `run()` rolls the whole
	transaction back when anything throws, so a weighing morning that called
	the endpoint once per cow lost every cow already written the moment one was
	refused — while still reporting them as recorded. record_weights() calls
	this inside a savepoint instead, and undoes only the row that failed.
	"""
	if not d.get("animal"):
		frappe.throw(_("Select an animal."))
	weight = flt(d.get("weight_kg"))
	if weight <= 0:
		frappe.throw(_("Weight must be greater than zero."))
	doc = frappe.new_doc("Livestock Weight Record")
	doc.animal = d.get("animal")
	doc.company = company_or_throw(d.get("company"))
	weight_date, is_backdated = backdate.resolve(d, "weight_date")
	backdate.assert_allowed(is_backdated)
	doc.weight_date = weight_date
	backdate.stamp(doc, is_backdated)
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
