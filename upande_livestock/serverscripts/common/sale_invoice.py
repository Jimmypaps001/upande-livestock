# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Everything a livestock Sales Invoice needs, worked out once.

Selling a culled animal used to take a buyer's name and a price, and the draft
invoice was left for Accounts to complete. Here the buyer is a real Customer and
every other header the invoice needs is found from it, the herd and the settings:

    company, currency, price list     -> the asset's company, Selling Settings
    payment terms and due date        -> the buyer's terms, or the disposal date
    Debit To (receivable)             -> the buyer's Party Account for the company,
                                         the company default, then a KES trade
                                         debtors account
    cost centre                       -> herd, then the asset, Livestock Settings,
                                         the company (common/cost_center)
    farm, business unit               -> Livestock Settings "disposal" fields, then
                                         the buyer's own business unit
    taxes                             -> Livestock Settings template; none by default
                                         (livestock is invoiced without VAT rows)
    eTIMS                             -> sales type N, receipt type S, a payment type
                                         from the mode of payment (optional)

`resolve_terms` returns those as one dict; `missing` says what cannot be found, in
words the manager can act on; `apply_terms` writes them onto the draft invoice. The
desk preview, the approval and the posting all go through the same three, so what is
shown is what Accounts receives.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from upande_livestock.serverscripts.common import cost_center as cost_centers
from upande_livestock.serverscripts.common.company import default_company

SETTINGS = "Livestock Settings"
BASES = ("Per head", "Per kg")
PIN = re.compile(r"^[AP]\d{9}[A-Z]$")

# Terms kept on the Livestock Disposal, as `sale_<key>`.
STORED = (
	"company", "price_basis", "weight_kg", "rate", "payment_terms", "due_date", "mode_of_payment",
	"cost_center", "farm", "business_unit", "taxes_template", "debit_to",
)


def to_disposal(terms: dict) -> dict:
	number = ("weight_kg", "rate")
	return {"sale_" + k: (terms.get(k) or 0) if k in number else (terms.get(k) or None) for k in STORED}


def from_disposal(doc) -> dict:
	"""What the approval stored; empty keys are worked out again."""
	return {k: doc.get("sale_" + k) or None for k in STORED}


def _setting(field):
	try:
		if frappe.get_meta(SETTINGS).has_field(field):
			return frappe.db.get_single_value(SETTINGS, field) or None
	except Exception:
		pass
	return None


def _exists(doctype, name):
	return bool(name) and bool(frappe.db.exists("DocType", doctype)) and bool(frappe.db.exists(doctype, name))


def phone(raw):
	"""Kenyan numbers carry a leading 0 (farm convention): +254712345678 and 712345678 both become 0712345678."""
	digits = re.sub(r"[^\d+]", "", raw or "")
	if digits.startswith("+254"):
		digits = "0" + digits[4:]
	elif digits.startswith("254") and len(digits) == 12:
		digits = "0" + digits[3:]
	elif len(digits) == 9 and digits[0] in "17":
		digits = "0" + digits
	return digits


def company_currency(company):
	return frappe.get_cached_value("Company", company, "default_currency") or "KES"


def receivable_account(customer, company):
	"""The Debit To for this buyer, or None."""
	if customer:
		for row in frappe.get_all("Party Account", filters={"parenttype": "Customer", "parent": customer,
		                                                    "company": company}, fields=["account"]):
			if row.account:
				return row.account
		group = frappe.db.get_value("Customer", customer, "customer_group")
		if group:
			acct = frappe.db.get_value("Party Account", {"parenttype": "Customer Group", "parent": group,
			                                             "company": company}, "account")
			if acct:
				return acct
	acct = frappe.get_cached_value("Company", company, "default_receivable_account")
	if acct:
		return acct
	currency = company_currency(company)
	rows = frappe.get_all(
		"Account",
		filters={"company": company, "account_type": "Receivable", "is_group": 0, "disabled": 0,
		         "account_currency": ["in", [currency, ""]]},
		pluck="name", order_by="name asc",
	)
	for name in rows:
		if "trade debtors" in name.lower() and "local" in name.lower():
			return name
	for name in rows:
		if "trade debtors" in name.lower():
			return name
	return None


def customer_card(customer, company=None):
	"""What the form shows about the buyer once picked."""
	c = frappe.db.get_value(
		"Customer", customer,
		["name", "customer_name", "customer_type", "tax_id", "mobile_no", "email_id", "customer_group",
		 "territory", "default_currency", "default_price_list", "payment_terms", "disabled",
		 "customer_primary_address", "customer_primary_contact"],
		as_dict=True,
	)
	if not c:
		return None
	company = company or default_company()
	c["address"] = ""
	if c.customer_primary_address:
		try:
			from frappe.contacts.doctype.address.address import get_address_display
			c["address"] = (get_address_display(c.customer_primary_address) or "").replace("<br>", ", ")
			c["address"] = re.sub(r"<[^>]+>", "", c["address"]).strip(", \n")
		except Exception:
			c["address"] = ""
	if c.customer_primary_contact and not (c.mobile_no or c.email_id):
		c["mobile_no"] = frappe.db.get_value("Contact", c.customer_primary_contact, "mobile_no")
	c["receivable"] = receivable_account(customer, company) if company else None
	c["disabled"] = int(c.disabled or 0)
	return c


def _due_date(template, posting_date):
	if template:
		try:
			from erpnext.accounts.party import get_due_date_from_template
			return getdate(get_due_date_from_template(template, posting_date, posting_date))
		except Exception:
			pass
	return getdate(posting_date)


def _payment_type_code(mode, due_date, posting_date):
	if mode:
		kind, name = frappe.db.get_value("Mode of Payment", mode, ["type", "name"]) or (None, mode)
		low = (name or "").lower()
		if kind == "Phone" or "mpesa" in low or "m-pesa" in low:
			return "06"
		if "cheque" in low or "check" in low:
			return "04"
		if "card" in low:
			return "05"
		return "01"
	return "02" if getdate(due_date) > getdate(posting_date) else "01"


def resolve_terms(animal, customer, price=None, posting_date=None, **given) -> dict:
	"""The full set of invoice terms for selling `animal` to `customer`.

	`given` carries what the person chose on the form (payment_terms, due_date,
	mode_of_payment, cost_center, farm, business_unit, taxes_template, debit_to,
	price_basis, weight_kg, rate); anything given wins, anything blank is worked out.
	Never raises on missing data: `missing` reports it.
	"""
	posting_date = getdate(posting_date or today())
	a = frappe.db.get_value("Animal", animal, ["asset_link", "current_herd", "last_weight_kg"], as_dict=True) or {}
	asset = a.get("asset_link")
	asset_row = frappe.db.get_value("Asset", asset, ["company", "cost_center", "item_code"], as_dict=True) if asset else None
	company = given.get("company") or (asset_row and asset_row.company) or default_company()
	cust_fields = ["payment_terms", "default_price_list", "default_currency"]
	if frappe.get_meta("Customer").has_field("custom_business_unit"):
		cust_fields.append("custom_business_unit")
	cust = (frappe.db.get_value("Customer", customer, cust_fields, as_dict=True)
	        if customer and frappe.db.exists("Customer", customer) else None)
	cust = cust or {}

	basis = given.get("price_basis") if given.get("price_basis") in BASES else "Per head"
	weight = flt(given.get("weight_kg")) or flt(a.get("last_weight_kg"))
	rate = flt(given.get("rate"))
	if basis == "Per kg":
		amount = round(rate * weight, 2)
	else:
		amount = flt(price)
		weight = flt(given.get("weight_kg")) or None
		rate = None

	terms_tpl = given.get("payment_terms") or cust.get("payment_terms") or None
	if terms_tpl and not _exists("Payment Terms Template", terms_tpl):
		terms_tpl = None
	due = getdate(given.get("due_date")) if given.get("due_date") else _due_date(terms_tpl, posting_date)
	if due < posting_date:
		due = posting_date

	herd = a.get("current_herd")
	cc = given.get("cost_center")
	if not cost_centers.usable(cc, company):
		cc = (cost_centers.herd_cost_center(herd, company)
		      or (asset_row and cost_centers.usable(asset_row.cost_center, company) and asset_row.cost_center)
		      or cost_centers.setting_cost_center(company)
		      or cost_centers.company_cost_center(company))

	farm = given.get("farm") or _setting("custom_disposal_farm") or _setting("custom_farm")
	if not _exists("Farm", farm):
		farm = _setting("custom_si_farm") if _exists("Farm", _setting("custom_si_farm")) else None
	bu = given.get("business_unit") or _setting("custom_disposal_business_unit") \
		or _setting("custom_milk_business_unit") or cust.get("custom_business_unit")
	if not _exists("Business Unit", bu):
		bu = None

	tax = given.get("taxes_template") or _setting("custom_sale_taxes_template")
	if tax and not _exists("Sales Taxes and Charges Template", tax):
		tax = None

	mode = given.get("mode_of_payment") or None
	if mode and not _exists("Mode of Payment", mode):
		mode = None

	return {
		"animal": animal, "customer": customer, "asset": asset, "item_code": asset_row and asset_row.item_code,
		"company": company, "currency": company_currency(company), "posting_date": str(posting_date),
		"price_list": frappe.db.get_single_value("Selling Settings", "selling_price_list") or cust.get("default_price_list"),
		"price_basis": basis, "weight_kg": weight or None, "rate": rate, "amount": amount,
		"payment_terms": terms_tpl, "due_date": str(due), "mode_of_payment": mode,
		"payment_type_code": _payment_type_code(mode, due, posting_date),
		"cost_center": cc or None, "farm": farm or None, "business_unit": bu or None, "taxes_template": tax,
		"debit_to": given.get("debit_to") or receivable_account(customer, company),
		"customer_currency": cust.get("default_currency"),
	}


def missing(terms) -> list:
	"""What stops a complete draft, one plain sentence each. Empty means the invoice will save."""
	out = []
	customer = terms.get("customer")
	if not customer:
		return [_("Choose the buyer (a Customer) the invoice is raised to.")]
	row = frappe.db.get_value("Customer", customer, ["disabled", "default_currency"], as_dict=True)
	if not row:
		return [_("{0} is not a Customer.").format(customer)]
	if row.disabled:
		out.append(_("Customer {0} is disabled. Enable it or choose another buyer.").format(customer))
	if flt(terms.get("amount")) <= 0:
		if terms.get("price_basis") == "Per kg":
			out.append(_("Per kg needs a rate and a weight: weigh her or type the weight."))
		else:
			out.append(_("Set the price she is being sold for."))
	if not terms.get("company"):
		out.append(_("No company: set Livestock Settings > Default Company."))
	currency = terms.get("currency")
	if row.default_currency and currency and row.default_currency != currency:
		out.append(_("Customer {0} is billed in {1}; a livestock sale is invoiced in {2}. "
		             "Choose a local buyer or change the Customer's billing currency.").format(
			customer, row.default_currency, currency))
	if not terms.get("debit_to"):
		out.append(_("Customer {0} has no receivable account for {1}. Add a Default Account row on the Customer.")
		           .format(customer, terms.get("company") or ""))
	if not terms.get("cost_center"):
		out.append(_("No cost centre found: set one on her herd or in Livestock Settings > Default Cost Centres by Company."))
	if not terms.get("price_list"):
		out.append(_("No selling price list: set one in Selling Settings."))
	return out


def assert_ready(terms):
	issues = missing(terms)
	if issues:
		frappe.throw("<br>".join(issues), title=_("The sale invoice cannot be drafted"))


def apply_terms(si, terms):
	"""Write the terms onto a draft Sales Invoice built by ERPNext's make_sales_invoice."""
	meta = si.meta

	def put(field, value):
		if value not in (None, "") and meta.has_field(field):
			si.set(field, value)

	si.customer = terms["customer"]
	si.company = terms["company"]
	si.currency = terms["currency"]
	si.conversion_rate = 1
	si.set_posting_time = 1
	si.posting_date = terms["posting_date"]
	si.update_stock = 0
	if terms.get("price_list"):
		si.selling_price_list = terms["price_list"]
		si.price_list_currency = frappe.db.get_value("Price List", terms["price_list"], "currency") or terms["currency"]
		si.plc_conversion_rate = 1

	# Buyer details ERPNext would copy on a normal invoice: address, contact, PIN, group.
	try:
		from erpnext.accounts.party import get_party_details
		details = get_party_details(party=terms["customer"], party_type="Customer", company=terms["company"],
		                            posting_date=terms["posting_date"], currency=terms["currency"],
		                            doctype="Sales Invoice", ignore_permissions=True)
		for key in ("customer_name", "tax_id", "territory", "customer_group", "customer_address", "address_display",
		            "contact_person", "contact_display", "contact_email", "contact_mobile", "shipping_address_name"):
			if details.get(key):
				put(key, details[key])
	except Exception:
		frappe.log_error(message=frappe.get_traceback(), title="Livestock sale: party details")

	si.debit_to = terms["debit_to"]
	if terms.get("payment_terms"):
		si.payment_terms_template = terms["payment_terms"]
		si.set("payment_schedule", [])
	si.due_date = terms["due_date"]

	put("farm", terms.get("farm"))
	put("custom_farm", terms.get("farm"))
	put("business_unit", terms.get("business_unit"))
	put("custom_business_unit", terms.get("business_unit"))

	if terms.get("taxes_template"):
		try:
			from erpnext.controllers.accounts_controller import get_taxes_and_charges
			si.taxes_and_charges = terms["taxes_template"]
			si.set("taxes", [])
			for row in get_taxes_and_charges("Sales Taxes and Charges Template", terms["taxes_template"]):
				si.append("taxes", row)
		except Exception:
			frappe.log_error(message=frappe.get_traceback(), title="Livestock sale: taxes template")

	# eTIMS (kenya_etims_compliance): the codes it reads when Accounts signs the invoice.
	put("custom_sales_type_code", "N")
	put("custom_receipt_type_code", "S")
	put("custom_payment_type_code", terms.get("payment_type_code"))

	remarks = _("Livestock sale - {0}").format(terms.get("asset") or terms.get("animal"))
	if terms.get("mode_of_payment"):
		remarks += _(". Payment: {0}").format(terms["mode_of_payment"])
	si.remarks = remarks

	row = si.items[0]
	row.qty = 1
	row.rate = terms["amount"]
	row.price_list_rate = terms["amount"]
	row.discount_percentage = 0
	if terms.get("cost_center"):
		row.cost_center = terms["cost_center"]
	for field, key in (("farm", "farm"), ("business_unit", "business_unit")):
		if terms.get(key) and row.meta.has_field(field):
			row.set(field, terms[key])
	return si


def lines(si, terms):
	"""The preview rows and totals of a built (unsaved) invoice."""
	try:
		si.calculate_taxes_and_totals()
	except Exception:
		pass
	return {
		"lines": [
			{"item_code": r.item_code, "item_name": r.item_name, "asset": r.get("asset"), "qty": flt(r.qty),
			 "uom": r.uom, "rate": flt(r.rate), "amount": flt(r.amount),
			 "income_account": r.income_account, "cost_center": r.cost_center}
			for r in si.items
		],
		"taxes": [{"description": t.description or t.account_head, "rate": flt(t.rate),
		           "amount": flt(t.tax_amount)} for t in si.get("taxes") or []],
		"net_total": flt(si.net_total) or flt(terms.get("amount")),
		"grand_total": flt(si.grand_total) or flt(terms.get("amount")),
		"tax_label": (si.get("taxes_and_charges") or _("No VAT rows (livestock sale)")) if not si.get("taxes") else
		             ", ".join(t.description or t.account_head for t in si.taxes),
	}
