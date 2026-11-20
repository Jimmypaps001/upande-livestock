# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Finish a waiting loss: post the write-off or release the sale once the claim lets it go."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import loss
from upande_livestock.serverscripts.common.envelope import guard, run


@frappe.whitelist()
def complete_loss(payload=None, loss_name=None, customer=None, sale_price=None, buyer_name=None):
	"""Finish a loss that is waiting: post the write-off, or release the sale
	(buyer and price) now that the claim lets it go. Refuses, with the reason,
	while the claim has not got far enough."""

	def go():
		guard("Livestock Disposal")
		d = loss.merge(payload, loss_name=loss_name, customer=customer, sale_price=sale_price,
		           buyer_name=buyer_name)
		name = d.get("loss_name") or d.get("loss")
		if not name or not frappe.db.exists("Livestock Loss", name):
			frappe.throw(_("Choose the loss."))
		animal = frappe.db.get_value("Livestock Loss", name, "animal")
		message = loss.sale_gate_message(animal)
		result = loss.advance(name, loss.sale(d))
		if result == "Awaiting claim":
			frappe.throw(message or _("The sale is waiting for the insurance claim."))
		if result == "Sale waiting":
			frappe.throw(_("Choose the Customer and the sale price to complete the sale."))
		return {"ok": True, "name": name, "status": result}

	return run(go, "livestock complete_loss failed")
