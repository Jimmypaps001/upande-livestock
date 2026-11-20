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

def _sell_livestock_asset(
	animal=None,
	asset_name=None,
	customer=None,
	selling_amount=None,
	posting_date=None,
	farm=None,
	business_unit=None,
):
	animal_name = animal or asset_name
	posting_date = posting_date or frappe.utils.today()
	farm = farm or ""
	business_unit = business_unit or ""

	if not animal_name:
		frappe.throw("animal is required")
	if not customer:
		frappe.throw("customer is required")
	if not selling_amount:
		frappe.throw("selling_amount is required")

	selling_amount = float(selling_amount)

	animal_doc = frappe.get_doc("Animal", animal_name)
	asset_name = animal_doc.asset_link
	if not asset_name:
		frappe.throw(
			"Animal "
			+ str(animal_name)
			+ " is not capitalised (no linked Asset); cannot sell as fixed asset."
		)
	asset = frappe.get_doc("Asset", asset_name)

	if asset.docstatus != 1:
		frappe.throw("Asset must be submitted before selling")

	if asset.status in ("Cancelled", "Sold", "Scrapped"):
		frappe.throw("Asset is already " + asset.status)

	company = asset.company
	company_currency = frappe.get_cached_value("Company", company, "default_currency") or "KES"

	# ERPNext's own builder: it puts the asset on the invoice as a fixed-asset row,
	# takes the company's disposal account and depreciation cost centre, and copies
	# the Asset's accounting dimensions. Submitting the invoice is what sells the
	# Asset (status Sold) and books the gain or loss against the disposal account.
	# This used to be a hand-built invoice that guessed every account itself.
	si = make_asset_sales_invoice(asset_name, asset.item_code or "herd", company)
	si.customer = customer
	si.currency = company_currency
	si.conversion_rate = 1
	# Without set_posting_time ERPNext resets posting_date to today on
	# insert, and the due date (the disposal date) then falls before it:
	# "Due Date cannot be before Posting Date". A cull approved a day
	# after it was raised never got its invoice.
	si.set_posting_time = 1
	si.posting_date = posting_date
	si.due_date = posting_date
	si.update_stock = 0
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	if price_list:
		si.selling_price_list = price_list
		si.price_list_currency = frappe.db.get_value("Price List", price_list, "currency") or company_currency
		si.plc_conversion_rate = 1
	si.remarks = "Livestock sale - " + asset_name
	if farm and si.meta.has_field("custom_farm"):
		si.custom_farm = farm
	if business_unit and si.meta.has_field("custom_business_unit"):
		si.custom_business_unit = business_unit
	row = si.items[0]
	row.qty = 1
	row.rate = selling_amount
	row.price_list_rate = selling_amount
	row.discount_percentage = 0
	row.description = "Livestock sale: " + (asset.asset_name or asset_name)

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
