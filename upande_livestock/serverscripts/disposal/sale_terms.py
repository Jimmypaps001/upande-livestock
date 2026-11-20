# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The invoice a livestock sale would raise, shown before it is agreed."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import sale_invoice
from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run


@frappe.whitelist()
def sale_terms(payload):
	"""Buyer card, resolved invoice terms, preview lines and anything still missing.

	payload: animal, customer, posting_date, and what the form chose: sale_price
	(per head) or rate and weight_kg (per kg), payment_terms, due_date,
	mode_of_payment, cost_center, farm, business_unit, taxes_template.
	Read-only: it builds the invoice in memory and saves nothing. The approval
	(approve_cull) recomputes the same terms on the server, so nothing here is trusted."""

	def go():
		guard_read("Livestock Disposal")
		d = as_dict(payload)
		animal, customer = d.get("animal"), d.get("customer")
		if not animal or not frappe.db.exists("Animal", animal):
			frappe.throw(_("Choose the animal being sold."))
		given = {k: d.get(k) for k in sale_invoice.STORED if d.get(k) not in (None, "")}
		terms = sale_invoice.resolve_terms(animal, customer, d.get("sale_price"), d.get("posting_date"), **given)
		issues = sale_invoice.missing(terms) if customer else []
		out = {
			"ok": True,
			"customer": sale_invoice.customer_card(customer, terms["company"]) if customer and frappe.db.exists("Customer", customer) else None,
			"terms": terms,
			"missing": issues,
			"notes": [],
			"lines": [], "taxes": [],
			"options": {
				"payment_terms": frappe.get_all("Payment Terms Template", pluck="name", order_by="name asc", limit_page_length=100),
				"modes_of_payment": frappe.get_all("Mode of Payment", filters={"enabled": 1}, pluck="name", order_by="name asc"),
			},
			"weight_kg": terms.get("weight_kg") or frappe.db.get_value("Animal", animal, "last_weight_kg"),
		}
		if not terms.get("asset"):
			out["notes"].append(_("She is not capitalised, so the sale is recorded without a Sales Invoice."))
		elif customer and not issues:
			try:
				from upande_livestock.serverscripts.disposal.sell_livestock_asset import build_sale_invoice

				si, _a, _asset, built = build_sale_invoice(animal, customer, terms["amount"], terms["posting_date"], terms=terms)
				out.update(sale_invoice.lines(si, built))
			except Exception as e:
				out["missing"].append(str(e))
		return out

	return run(go, "livestock sale_terms failed")
