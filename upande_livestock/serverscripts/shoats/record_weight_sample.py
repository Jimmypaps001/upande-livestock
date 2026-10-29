# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weigh N animals of a shoat herd and record their average: the herd's live weight follows."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import backdate, shoats
from upande_livestock.serverscripts.common.employee import current_employee
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


@frappe.whitelist()
def record_weight_sample(payload=None):
	def go():
		guard("Herd Weight Sample")
		d = as_dict(payload)
		herd = (d.get("herd") or "").strip()
		if not herd or not shoats.is_by_number(herd):
			frappe.throw(_("{0} is not a shoat herd.").format(herd))
		on, back = backdate.resolve(d, "sample_date")
		backdate.assert_not_future(on)
		backdate.assert_allowed(back)
		doc = frappe.get_doc({
			"doctype": "Herd Weight Sample", "herd": herd, "sample_date": on,
			"sample_class": d.get("sample_class") or "All",
			"animals_weighed": d.get("animals_weighed"), "average_kg": d.get("average_kg"),
			"operator": d.get("operator") or current_employee(), "remarks": d.get("remarks")})
		doc.flags.ignore_permissions = True
		doc.insert()
		return {
			"ok": True, "created": {"weight_sample": doc.name},
			"sample": {"name": doc.name, "sample_date": str(doc.sample_date), "sample_class": doc.sample_class,
			           "animals_weighed": doc.animals_weighed, "average_kg": doc.average_kg, "total_kg": doc.total_kg},
			"herd": herd, "head": shoats.head(herd), **shoats.live_weight(herd), "warnings": [],
		}

	return run(go, "livestock record_weight_sample failed")
