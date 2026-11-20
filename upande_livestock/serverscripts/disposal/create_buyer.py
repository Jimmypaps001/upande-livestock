# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Add a buyer (Customer) from the sale form, with what the books need."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import culling, sale_invoice
from upande_livestock.serverscripts.common.company import default_company
from upande_livestock.serverscripts.common.envelope import as_dict, guard_write, run


def _first(doctype, *names):
	for n in names:
		if n and frappe.db.exists(doctype, n):
			return n
	return None


def _leaf(doctype, *names):
	"""A usable group: the first name that exists, else any non-group row."""
	hit = _first(doctype, *names)
	if hit:
		return hit
	return frappe.db.get_value(doctype, {"is_group": 0}, "name")


@frappe.whitelist()
def create_buyer(payload):
	"""Create a Customer for a livestock sale, or return the one already called that.

	The manager who approves a sale may add the buyer, so this is the manager's
	(assert_manager) and the Customer is inserted with ignore_permissions. It fills
	what a draft invoice needs and live makes mandatory on Customer: type, billing
	currency, price list, payment terms, business unit and the receivable account
	for the company. KRA PIN is optional but checked for shape; a phone number
	becomes a linked Contact so it shows on the invoice."""

	def go():
		guard_write("Livestock Disposal")
		culling.assert_manager()
		d = as_dict(payload)
		name = (d.get("customer_name") or "").strip()
		if not name:
			frappe.throw(_("Give the buyer's name."))
		existing = frappe.db.get_value("Customer", {"customer_name": name}, "name") or (
			name if frappe.db.exists("Customer", name) else None)
		if existing:
			return {"ok": True, "name": existing, "existing": True}
		pin = (d.get("tax_id") or "").strip().upper()
		if pin and not sale_invoice.PIN.match(pin):
			frappe.throw(_("A KRA PIN looks like A123456789B (a letter, nine digits, a letter)."))
		number = sale_invoice.phone(d.get("phone"))
		if not number:
			frappe.throw(_("Give a phone number so Accounts can reach the buyer."))
		company = default_company()
		meta = frappe.get_meta("Customer")
		terms_tpl = _first("Payment Terms Template", d.get("payment_terms"), "0 days", "Cash before collection")
		bu = None
		for f in ("custom_disposal_business_unit", "custom_milk_business_unit"):
			bu = bu or frappe.db.get_single_value("Livestock Settings", f)
		doc = frappe.new_doc("Customer")
		doc.customer_name = name
		doc.customer_type = d.get("customer_type") if d.get("customer_type") in ("Individual", "Company", "Partnership") else "Individual"
		doc.tax_id = pin or None
		doc.customer_group = _leaf("Customer Group", "Individual", frappe.db.get_single_value("Selling Settings", "customer_group"))
		doc.territory = _leaf("Territory", "Kenya", frappe.db.get_single_value("Selling Settings", "territory"))
		doc.default_currency = sale_invoice.company_currency(company)
		doc.default_price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		if terms_tpl:
			doc.payment_terms = terms_tpl
		if meta.has_field("custom_business_unit") and bu:
			doc.custom_business_unit = bu
		account = sale_invoice.receivable_account(None, company)
		if account:
			doc.append("accounts", {"company": company, "account": account})
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)

		contact = frappe.get_doc({
			"doctype": "Contact", "first_name": name, "mobile_no": number,
			"phone_nos": [{"phone": number, "is_primary_mobile_no": 1}],
			"email_ids": [{"email_id": d["email"], "is_primary": 1}] if d.get("email") else [],
			"links": [{"link_doctype": "Customer", "link_name": doc.name}],
		})
		contact.insert(ignore_permissions=True)
		frappe.db.set_value("Customer", doc.name, {
			"customer_primary_contact": contact.name, "mobile_no": number, "email_id": d.get("email") or None,
		}, update_modified=False)
		return {"ok": True, "name": doc.name, "existing": False}

	return run(go, "livestock create_buyer failed")
