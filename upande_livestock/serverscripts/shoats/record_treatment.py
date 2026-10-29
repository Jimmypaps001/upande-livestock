# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Record a treatment, dipping, deworming or vaccination: number treated, drug from the Drug Store."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import backdate, shoats
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


@frappe.whitelist()
def record_treatment(payload=None):
	def go():
		guard("Herd Treatment")
		d = as_dict(payload)
		herd = (d.get("herd") or "").strip()
		if not herd or not shoats.is_by_number(herd):
			frappe.throw(_("{0} is not a shoat herd.").format(herd))
		on, back = backdate.resolve(d, "treatment_date")
		backdate.assert_not_future(on)
		backdate.assert_allowed(back)
		doc = frappe.get_doc({
			"doctype": "Herd Treatment", "herd": herd, "treatment_date": on,
			"treatment_type": d.get("treatment_type") or "Treatment", "product": d.get("product"),
			"dose_per_head": d.get("dose_per_head"), "number_treated": d.get("number_treated"),
			"withdrawal_days": d.get("withdrawal_days") or 0, "diagnosis": d.get("diagnosis"),
			"warehouse": d.get("warehouse") or None, "remarks": d.get("remarks"),
			"treated_by": d.get("operator") or current_employee()})
		if not doc.product:
			frappe.throw(_("Say which product was used."))
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		doc.reload()
		return {
			"ok": True, "created": {"treatment": doc.name, "stock_entry": doc.stock_entry or None},
			"treatment": {"name": doc.name, "treatment_date": str(doc.treatment_date),
			              "treatment_type": doc.treatment_type, "product": doc.product,
			              "product_name": doc.product_name, "number_treated": doc.number_treated,
			              "dose_per_head": doc.dose_per_head, "quantity": doc.quantity, "uom": doc.dose_uom,
			              "withdrawal_days": doc.withdrawal_days,
			              "withdrawal_end": str(doc.withdrawal_end) if doc.withdrawal_end else None},
			"herd": herd,
			"withdrawal_until": str(frappe.db.get_value("Herds", herd, "withdrawal_until") or "") or None,
			"warnings": [],
		}

	return run(go, "livestock record_treatment failed")
