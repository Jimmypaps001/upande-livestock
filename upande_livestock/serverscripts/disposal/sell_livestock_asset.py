"""Sell the Asset behind an animal, booking the gain or loss.

Guards Asset — same reasoning as scrapping, and this one takes a price."""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common.company import company_or_throw

KG = "Kg"


def _kg_uom():
	"""The kilogram UOM on this site (ERPNext ships it as "Kg")."""
	if frappe.db.exists("UOM", KG):
		return KG
	for name in ("Kilogram", "kg"):
		if frappe.db.exists("UOM", name):
			return name
	return frappe.get_doc({"doctype": "UOM", "uom_name": KG}).insert(ignore_permissions=True).name


def _sale_lines(animal_doc, asset, asset_name, amount, per_kg, weight, rate_per_kg,
                income_account, expense_account, cost_center, revenue_account=None):
	"""The Sales Invoice lines for one animal.

	ERPNext refuses a fixed-asset line selling more units than the Asset holds
	(one animal is one unit), so a capitalised animal sold per kg gets two
	lines: the kilograms, at the price per kg, on the sale item; and the Asset
	itself at nil, which is what disposes it and books its book value out.
	"""
	label = animal_doc.burn_name or animal_doc.name
	lines = []
	if per_kg:
		kg_item = _sale_item()
		uom = _kg_uom()
		stock_uom = _sell_in_kg(kg_item, uom)
		lines.append({
			"item_code": kg_item,
			"description": "Livestock sale: " + label,
			"stock_uom": stock_uom,
			"uom": uom,
			"conversion_factor": 1,
			"qty": weight,
			"rate": rate_per_kg,
			"price_list_rate": rate_per_kg,
			"discount_percentage": 0,
			"income_account": revenue_account or income_account,
			"expense_account": expense_account,
			"cost_center": cost_center,
		})
	if asset:
		lines.append({
			"item_code": asset.item_code or "herd",
			"item_name": asset.item_name or asset.asset_name or "herd",
			"description": "Livestock sale: " + (asset.asset_name or asset_name),
			"item_group": frappe.db.get_value("Item", asset.item_code, "item_group") if asset.item_code else None,
			"stock_uom": "Nos",
			"uom": "Nos",
			"conversion_factor": 1,
			"qty": 1,
			"rate": 0 if per_kg else amount,
			"price_list_rate": 0 if per_kg else amount,
			"discount_percentage": 0,
			"income_account": income_account,
			"expense_account": expense_account,
			"is_fixed_asset": 1,
			"asset": asset_name,
			"cost_center": cost_center,
		})
	return lines


def _sell_in_kg(item, uom):
	"""Make the sale item's stock UOM kilograms (idempotent) and return it.

	A kilogram quantity is fractional; ERPNext rejects fractions on a
	whole-number stock UOM such as Nos, so the item must count in kg itself.
	"""
	if frappe.db.get_value("UOM", uom, "must_be_whole_number"):
		frappe.db.set_value("UOM", uom, "must_be_whole_number", 0)
	if frappe.db.get_value("Item", item, "stock_uom") != uom:
		frappe.db.set_value("Item", item, "stock_uom", uom)
		frappe.get_doc("Item", item).clear_cache()
	if not frappe.db.exists("UOM Conversion Detail", {"parent": item, "uom": uom}):
		doc = frappe.get_doc("Item", item)
		doc.append("uoms", {"uom": uom, "conversion_factor": 1})
		doc.save(ignore_permissions=True)
	return uom


def _sale_item():
	"""The item a per-kg line is invoiced on: the Animal Sale Item setting."""
	item = frappe.db.get_single_value("Livestock Settings", "custom_animal_sale_item")
	if not item:
		frappe.throw(_("Set the Animal Sale Item in Livestock Settings to invoice a sale per kg."))
	return item



def _sell_livestock_asset(
	animal=None,
	asset_name=None,
	customer=None,
	selling_amount=None,
	posting_date=None,
	farm=None,
	business_unit=None,
	exit_weight_kg=None,
	price_per_kg=None,
):
	"""Invoice an animal's sale. Per kg when `exit_weight_kg` and `price_per_kg`
	are given (qty = kilograms, UOM Kg, rate = price per kg), else one lump-sum
	line as before. A capitalised animal also disposes its Asset; one that was
	never capitalised is invoiced against the Animal Sale Item."""
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
	per_kg = flt(exit_weight_kg) > 0 and flt(price_per_kg) > 0

	animal_doc = frappe.get_doc("Animal", animal_name)
	asset_name = animal_doc.asset_link
	asset = None
	if asset_name:
		asset = frappe.get_doc("Asset", asset_name)
		if asset.docstatus != 1:
			frappe.throw("Asset must be submitted before selling")
		if asset.status in ("Cancelled", "Sold", "Scrapped"):
			frappe.throw("Asset is already " + asset.status)
	elif not per_kg:
		frappe.throw(
			"Animal "
			+ str(animal_name)
			+ " is not capitalised (no linked Asset); cannot sell as fixed asset."
		)

	company = asset.company if asset else company_or_throw()

	company_doc = frappe.get_doc("Company", company)
	company_currency = company_doc.default_currency or "KES"
	default_receivable = company_doc.default_receivable_account
	default_expense = company_doc.default_expense_account
	default_cost_center = company_doc.cost_center
	default_income = company_doc.default_income_account

	asset_category = asset.asset_category if asset else None
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
	cost_center = (asset.cost_center if asset else None) or default_cost_center
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
			# Without set_posting_time ERPNext resets posting_date to today on
			# insert, and the due date (the disposal date) then falls before it:
			# "Due Date cannot be before Posting Date". A cull approved a day
			# after it was raised never got its invoice.
			"set_posting_time": 1,
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
			"remarks": "Livestock sale - " + (asset_name or animal_name),
			"items": _sale_lines(
				animal_doc, asset, asset_name, selling_amount, per_kg,
				flt(exit_weight_kg), flt(price_per_kg), income_account, expense_account, cost_center,
				# With an Asset line, proceeds go to the disposal account so the
				# ledger shows gain = proceeds - book value, not sales income.
				None if asset else default_income,
			),
		}
	)

	si.flags.ignore_pricing_rule = True
	si.flags.ignore_permissions = True
	si.insert(ignore_permissions=True)
	# A farm that routes its invoices through an approval workflow keeps them as
	# drafts for it; otherwise the sale is final and, for a capitalised animal,
	# submitting is what disposes the Asset.
	if not frappe.db.exists("Workflow", {"document_type": "Sales Invoice", "is_active": 1}):
		si.submit()

	# See scrap_livestock_asset: retirement belongs to api/animal.retire_animal(),
	# and this function does not commit.

	return {
		"success": True,
		"asset": asset_name,
		"sales_invoice": si.name,
		"workflow_state": si.get("workflow_state") or ("Submitted" if si.docstatus == 1 else "Draft"),
		"customer": customer,
		"selling_amount": selling_amount,
		"grand_total": si.grand_total,
		"currency": si.currency,
	}


@frappe.whitelist()
def sell_livestock_asset(animal=None, asset_name=None, customer=None, selling_amount=None, posting_date=None, farm=None, business_unit=None, exit_weight_kg=None, price_per_kg=None):
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
	return _sell_livestock_asset(animal=animal, asset_name=asset_name, customer=customer, selling_amount=selling_amount, posting_date=posting_date, farm=farm, business_unit=business_unit, exit_weight_kg=exit_weight_kg, price_per_kg=price_per_kg)
