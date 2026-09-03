"""Record a milking session for a herd.

Guards Milk Recording. The Stock Entry and Journal Entry it posts are made by
the controller with ignore_permissions, so this is the one check that matters."""

import frappe
from frappe import _
from frappe.utils import flt, nowtime, today

from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


@frappe.whitelist()
def create_milk_recording(payload):
	def go():
		guard("Milk Recording")
		d = as_dict(payload)
		herd = d.get("herd")
		if not herd:
			frappe.throw(_("Select a herd."))
		total = flt(d.get("total_yield_kg"))
		if total <= 0:
			frappe.throw(_("Total yield must be greater than zero."))
		discarded = flt(d.get("discarded_kg"))
		net = total - discarded
		if net < 0:
			frappe.throw(_("Discarded milk cannot exceed the total yield."))
		price = flt(d.get("price_per_kg"))

		company = (
			d.get("company")
			or frappe.db.get_single_value("Livestock Settings", "custom_default_company")
			or frappe.defaults.get_user_default("company")
		)
		if not company:
			frappe.throw(_("No company configured (Livestock Settings > Default Company)."))

		doc = frappe.new_doc("Milk Recording")
		doc.herd = herd
		doc.milking_time = d.get("milking_time") or nowtime()
		doc.recording_date = d.get("recording_date") or today()
		doc.cows_milked = int(flt(d.get("cows_milked")))
		doc.operator = d.get("operator") or current_employee()
		doc.company = company
		doc.total_yield_kg = total
		doc.discarded_kg = discarded
		doc.discard_reason = d.get("discard_reason") or None
		doc.discard_reason_notes = d.get("discard_reason_notes") or None
		# net_yield_kg / milk_revenue are read-only on the form (a client script
		# fills them there); server-side we must set them before submit because
		# the after-submit Stock Entry uses net_yield_kg.
		doc.net_yield_kg = net
		doc.price_per_kg = price
		doc.milk_revenue = net * price
		doc.cost_center = frappe.db.get_value("Herds", herd, "cost_center")
		doc.bulk_scc = flt(d.get("bulk_scc")) or None
		doc.protein_percent = flt(d.get("protein_percent")) or None
		doc.remarks = d.get("remarks")
		doc.insert()
		doc.submit()  # fires "Milk Recording After Submit - Stock Entry"
		doc.reload()

		return {
			"ok": True,
			"name": doc.name,
			"net_yield_kg": net,
			"revenue": doc.milk_revenue,
			"stock_entry": doc.stock_entry,
			"journal_entry": doc.journal_entry,
		}

	return run(go, "livestock create_milk_recording failed")
