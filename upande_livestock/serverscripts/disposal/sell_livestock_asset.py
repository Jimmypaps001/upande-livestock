"""Sell the Asset behind an animal, booking the gain or loss.

Guards Asset — same reasoning as scrapping, and this one takes a price."""

import frappe
from frappe import _


def make_asset_sales_invoice(asset, item_code, company):
	"""ERPNext's `make_sales_invoice` for one head. Its arguments differ by release
	(`sell_qty` was added in 16.x), so quantity is passed only if it is accepted."""
	from erpnext.assets.doctype.asset.asset import make_sales_invoice

	try:
		return make_sales_invoice(asset=asset, item_code=item_code, company=company, sell_qty=1)
	except TypeError:
		return make_sales_invoice(asset=asset, item_code=item_code, company=company)

def build_sale_invoice(animal_name, customer, selling_amount, posting_date, farm=None, business_unit=None, terms=None):
	"""The draft Sales Invoice for selling this animal, built and not yet saved.

	`terms` is what the sale form settled (sale_invoice.resolve_terms); a caller with
	none (the loss flow, the REST endpoint) gets the same terms worked out from
	defaults, so every sale is complete the same way."""
	from upande_livestock.serverscripts.common import sale_invoice

	animal_doc = frappe.get_doc("Animal", animal_name)
	asset_name = animal_doc.asset_link
	if not asset_name:
		frappe.throw(
			"Animal " + str(animal_name) + " is not capitalised (no linked Asset); cannot sell as fixed asset."
		)
	asset = frappe.get_doc("Asset", asset_name)
	if asset.docstatus != 1:
		frappe.throw("Asset must be submitted before selling")
	if asset.status in ("Cancelled", "Sold", "Scrapped"):
		frappe.throw("Asset is already " + asset.status)

	if not terms:
		terms = sale_invoice.resolve_terms(
			animal_name, customer, selling_amount, posting_date, farm=farm, business_unit=business_unit
		)
	else:
		terms = dict(terms, customer=customer, amount=float(selling_amount), posting_date=str(posting_date))
	sale_invoice.assert_ready(terms)

	# ERPNext's own builder: it puts the asset on the invoice as a fixed-asset row,
	# takes the company's disposal account and the Asset's accounting dimensions.
	# Submitting the invoice is what sells the Asset (status Sold) and books the gain
	# or loss against the disposal account. sale_invoice.apply_terms then fills the
	# buyer, terms, receivable, cost centre, farm, business unit, taxes and eTIMS
	# codes, so Accounts receives a draft that needs nothing typed.
	si = make_asset_sales_invoice(asset_name, asset.item_code or "herd", terms["company"])
	sale_invoice.apply_terms(si, terms)
	return si, asset_name, asset, terms


def _sell_livestock_asset(
	animal=None,
	asset_name=None,
	customer=None,
	selling_amount=None,
	posting_date=None,
	farm=None,
	business_unit=None,
	terms=None,
):
	animal_name = animal or asset_name
	posting_date = posting_date or frappe.utils.today()

	if not animal_name:
		frappe.throw("animal is required")
	if not customer:
		frappe.throw("customer is required")
	if not selling_amount:
		frappe.throw("selling_amount is required")

	selling_amount = float(selling_amount)
	si, asset_name, asset, terms = build_sale_invoice(
		animal_name, customer, selling_amount, posting_date, farm, business_unit, terms
	)

	si.flags.ignore_pricing_rule = True
	si.flags.ignore_permissions = True
	si.insert(ignore_permissions=True)

	from upande_livestock.serverscripts.disposal.notify_accounts import notify_sale_invoice

	notify_sale_invoice(animal_name, asset_name, customer, selling_amount, si.name, si.currency)

	# See scrap_livestock_asset: retirement belongs to api/animal.retire_animal(),
	# and this function does not commit.

	return {
		"success": True,
		"asset": asset_name,
		"sales_invoice": si.name,
		"workflow_state": si.workflow_state or "Draft",
		"customer": customer,
		"selling_amount": selling_amount,
		"grand_total": si.grand_total,
		"currency": si.currency,
	}


@frappe.whitelist()
def sell_livestock_asset(animal=None, asset_name=None, customer=None, selling_amount=None, posting_date=None, farm=None, business_unit=None):
	"""REST entry point. The guard lives here, not in `_sell_livestock_asset`.

	`_sell_livestock_asset` is also called from
	`doctype/livestock_disposal/livestock_disposal.py` after the Disposal
	submits, inside a try/except that downgrades any failure to a toast. A guard
	in the shared function would therefore be swallowed: the animal would retire
	and the Journal Entry would silently never post. The desk path has already
	been permission-checked by the Disposal itself.

	Asset *write*, not create — this amends an existing Asset rather than making
	one. The Journal Entry and Sales Invoice it posts are inserted with
	ignore_permissions, so this is the only check standing.
	"""
	if not frappe.has_permission("Asset", "write"):
		frappe.throw(_("You are not permitted to sell a livestock Asset."), frappe.PermissionError)
	return _sell_livestock_asset(animal=animal, asset_name=asset_name, customer=customer, selling_amount=selling_amount, posting_date=posting_date, farm=farm, business_unit=business_unit)
