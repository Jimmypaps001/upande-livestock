# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A manager's signature on an animal leaving."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.common.envelope import as_dict, guard_write, run


@frappe.whitelist()
def approve_cull(payload):
	"""Approve a case, and settle the terms it cannot be posted without.

	A sale needs a buyer and a price at this point rather than at posting: the
	approval IS of those terms, and approving an unpriced sale would be signing
	a blank cheque for whoever posts it afterwards.
	"""

	def go():
		guard_write("Livestock Disposal")
		culling.assert_manager()
		d = as_dict(payload)
		name = (d.get("case") or "").strip()
		if not frappe.db.exists("Livestock Disposal", name):
			frappe.throw(_("{0} is not a cull case.").format(name))

		doc = frappe.get_doc("Livestock Disposal", name)
		culling.assert_at(doc, {culling.AWAITING_APPROVAL}, "approved")

		needs = culling.requires(doc.custom_cull_flow)
		changes = {
			"custom_review_status": culling.APPROVED,
			"custom_approved_by": frappe.session.user,
			"custom_approved_on": today(),
		}
		if needs["price"]:
			price = flt(d.get("sale_price") or doc.sale_price)
			buyer = d.get("buyer_name") or doc.buyer_name or d.get("customer") or doc.customer
			if price <= 0:
				frappe.throw(_("Set the price she is being sold for before approving it."))
			if not buyer:
				frappe.throw(_("Say who is buying her before approving the sale."))
			changes["sale_price"] = price
			if d.get("buyer_name"):
				changes["buyer_name"] = d["buyer_name"]
			if d.get("customer"):
				changes["customer"] = d["customer"]
			if d.get("buyer_contact"):
				changes["buyer_contact"] = d["buyer_contact"]

		doc.db_set(changes, update_modified=False)
		return {"ok": True, "name": name, "status": culling.APPROVED}

	return run(go, "livestock approve_cull failed")
