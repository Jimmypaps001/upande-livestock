# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A manager's signature on an animal leaving."""

import frappe
from frappe import _
from frappe.utils import flt, today

from upande_livestock.serverscripts.common import culling, sale_invoice
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
			customer = d.get("customer") or doc.customer
			if not customer:
				frappe.throw(_("Choose the buyer, a Customer, before approving the sale. A name typed in cannot be invoiced."))
			# The terms of the draft invoice are settled with the sale: what the form
			# chose wins, the rest is worked out, and anything the invoice would still
			# lack stops the approval rather than reaching Accounts half empty.
			given = {k: d.get(k) for k in sale_invoice.STORED if d.get(k) not in (None, "")}
			if not given:
				given = sale_invoice.from_disposal(doc)
			given = {k: v for k, v in given.items() if v}
			terms = sale_invoice.resolve_terms(
				doc.animal, customer, price if price > 0 else None, doc.disposal_date, **given
			)
			if not (price > 0 or terms["amount"] > 0):
				frappe.throw(_("Set the price she is being sold for before approving it."))
			price = terms["amount"]
			sale_invoice.assert_ready(terms)
			changes.update(sale_invoice.to_disposal(terms))
			changes["sale_price"] = price
			changes["customer"] = customer
			changes["buyer_name"] = d.get("buyer_name") or frappe.db.get_value("Customer", customer, "customer_name")
			if d.get("buyer_contact"):
				changes["buyer_contact"] = d["buyer_contact"]
			else:
				contact = sale_invoice.customer_card(customer, terms["company"]) or {}
				if contact.get("mobile_no"):
					changes["buyer_contact"] = contact["mobile_no"]

		doc.db_set(changes, update_modified=False)
		return {"ok": True, "name": name, "status": culling.APPROVED}

	return run(go, "livestock approve_cull failed")
