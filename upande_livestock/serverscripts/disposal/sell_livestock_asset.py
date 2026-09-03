"""Sell the Asset behind an animal, booking the gain or loss.

Guards Asset — same reasoning as scrapping, and this one takes a price."""

import frappe
from frappe import _



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

	company_doc = frappe.get_doc("Company", company)
	company_currency = company_doc.default_currency or "KES"
	default_receivable = company_doc.default_receivable_account
	default_expense = company_doc.default_expense_account
	default_cost_center = company_doc.cost_center
	default_income = company_doc.default_income_account

	asset_category = asset.asset_category
	category_fixed_asset_account = None

	if asset_category:
		cat_doc = frappe.get_doc("Asset Category", asset_category)
		for row in cat_doc.accounts:
			if row.company_name == company:
				category_fixed_asset_account = row.fixed_asset_account
				break

	disposal_account = None
	try:
		disposal_account = frappe.get_cached_value("Company", company, "disposal_account")
	except Exception:
		pass

	if not disposal_account:
		try:
			disposal_account = frappe.get_cached_value("Company", company, "gain_loss_on_asset_disposal")
		except Exception:
			pass

	if not disposal_account:
		disposal_account = category_fixed_asset_account or default_income

	income_account = disposal_account or default_income
	expense_account = default_expense
	cost_center = asset.cost_center or default_cost_center
	debit_to = default_receivable

	default_price_list = frappe.db.get_value("Selling Settings", None, "selling_price_list") or ""
	price_list_currency = company_currency
	plc_conversion_rate = 1

	if default_price_list:
		pl_currency = frappe.db.get_value("Price List", default_price_list, "currency")
		if pl_currency:
			price_list_currency = pl_currency
			if pl_currency != company_currency:
				try:
					plc_conversion_rate = (
						frappe.db.get_value(
							"Currency Exchange",
							{"from_currency": pl_currency, "to_currency": company_currency},
							"exchange_rate",
							order_by="date desc",
						)
						or 1
					)
				except Exception:
					plc_conversion_rate = 1

	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": customer,
			"company": company,
			"posting_date": posting_date,
			"due_date": posting_date,
			"naming_series": "SINV-.YYYY.-",
			"currency": company_currency,
			"conversion_rate": 1,
			"selling_price_list": default_price_list,
			"price_list_currency": price_list_currency,
			"plc_conversion_rate": plc_conversion_rate,
			"debit_to": debit_to,
			"update_stock": 0,
			"custom_farm": farm,
			"custom_business_unit": business_unit,
			"remarks": "Livestock sale - " + asset_name,
			"items": [
				{
					"item_code": asset.item_code or "herd",
					"item_name": asset.item_name or asset.asset_name or "herd",
					"description": "Livestock sale: " + (asset.asset_name or asset_name),
					"item_group": "Assets",
					"stock_uom": "Nos",
					"uom": "Nos",
					"conversion_factor": 1,
					"qty": 1,
					"rate": selling_amount,
					"price_list_rate": selling_amount,
					"discount_percentage": 0,
					"income_account": income_account,
					"expense_account": expense_account,
					"is_fixed_asset": 1,
					"asset": asset_name,
					"cost_center": cost_center,
				}
			],
		}
	)

	si.flags.ignore_pricing_rule = True
	si.flags.ignore_permissions = True
	si.insert(ignore_permissions=True)

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
