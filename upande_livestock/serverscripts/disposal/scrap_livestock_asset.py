"""Scrap the Asset behind an animal that died or was culled.

Guards Asset. It had no permission check at all, and it writes off money:
a phone authenticating as a real user makes that gap a real one."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import guard


@frappe.whitelist()
def scrap_livestock_asset(animal=None, asset_name=None, reason=None, scrapping_date=None):
	guard("Asset")
	animal_name = animal or asset_name
	reason = reason or ""
	scrapping_date = scrapping_date or frappe.utils.today()

	if not animal_name:
		frappe.throw("animal is required")

	animal_doc = frappe.get_doc("Animal", animal_name)
	asset_name = animal_doc.asset_link
	if not asset_name:
		frappe.throw("Animal " + str(animal_name) + " is not capitalised (no linked Asset); cannot scrap.")

	asset = frappe.get_doc("Asset", asset_name)

	if asset.docstatus != 1:
		frappe.throw("Asset must be submitted before scrapping")

	if asset.status in ("Cancelled", "Sold", "Scrapped"):
		frappe.throw("Asset is already " + asset.status)

	company = asset.company

	# ── Fetch Company defaults ──
	company_doc = frappe.get_doc("Company", company)
	company_disposal_account = getattr(company_doc, "disposal_account", None)
	company_dep_expense_account = getattr(company_doc, "depreciation_expense_account", None)
	company_dep_cost_center = getattr(company_doc, "depreciation_cost_center", None)
	company_default_cost_center = company_doc.cost_center

	# ── Fetch accounts from Asset Category ──
	asset_category = asset.asset_category
	category_fixed_asset_account = None
	category_accumulated_dep = None
	category_dep_expense = None

	if asset_category:
		cat_doc = frappe.get_doc("Asset Category", asset_category)
		for row in cat_doc.accounts:
			if row.company_name == company:
				category_fixed_asset_account = row.fixed_asset_account
				category_accumulated_dep = getattr(row, "accumulated_depreciation_account", None)
				category_dep_expense = getattr(row, "depreciation_expense_account", None)
				break

	# ── Resolve Disposal Account ──
	# Priority: Company disposal account > Asset Category fixed asset account > search by name
	disposal_account = company_disposal_account

	if not disposal_account:
		try:
			disposal_account = frappe.get_cached_value("Company", company, "gain_loss_on_asset_disposal")
		except Exception:
			pass

	if not disposal_account:
		disposal_account = frappe.db.get_value(
			"Account", {"company": company, "account_name": ["like", "%Gain%Loss%Asset%"]}, "name"
		)

	# ── Resolve Depreciation Expense Account ──
	# Priority: Asset Category > Company > search by name
	depreciation_expense_account = category_dep_expense or company_dep_expense_account

	if not depreciation_expense_account:
		depreciation_expense_account = frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Expense", "account_name": ["like", "%Depreciation%"]},
			"name",
		)

	if not disposal_account or not depreciation_expense_account:
		frappe.throw(
			"Please set Disposal Account and Depreciation Expense Account in Company "
			+ company
			+ " or in Asset Category "
			+ (asset_category or "(none)")
		)

	# ── Resolve Cost Center: asset-level > company depreciation cost center > company default ──
	cost_center = asset.cost_center or company_dep_cost_center or company_default_cost_center or ""

	# ── Resolve Accumulated Depreciation Account for write-off ──
	accumulated_dep_account = category_accumulated_dep
	if not accumulated_dep_account:
		accumulated_dep_account = getattr(company_doc, "accumulated_depreciation_account", None)

	# ── Calculate values ──
	gross_amount = asset.gross_purchase_amount or 0
	accumulated_depreciation = asset.opening_accumulated_depreciation or 0
	value_after_dep = (
		asset.value_after_depreciation if asset.value_after_depreciation is not None else gross_amount
	)

	# ── Create Journal Entry ──
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Depreciation Entry"
	je.naming_series = "ACC-JV-.YYYY.-"
	je.company = company
	je.posting_date = scrapping_date
	je.remark = "Scrap Entry for asset " + asset_name + (". Reason: " + reason if reason else "")

	# Debit the disposal account (write off the remaining value)
	je.append(
		"accounts",
		{
			"account": disposal_account,
			"debit_in_account_currency": value_after_dep,
			"cost_center": cost_center,
		},
	)

	# If there is accumulated depreciation, debit it to clear the balance
	if accumulated_depreciation and accumulated_dep_account:
		je.append(
			"accounts",
			{
				"account": accumulated_dep_account,
				"debit_in_account_currency": accumulated_depreciation,
				"cost_center": cost_center,
			},
		)
		# Credit the fixed asset account for the full gross amount
		credit_account = category_fixed_asset_account or depreciation_expense_account
		je.append(
			"accounts",
			{
				"account": credit_account,
				"credit_in_account_currency": gross_amount,
				"cost_center": cost_center,
				"reference_type": "Asset",
				"reference_name": asset_name,
			},
		)
	else:
		# Simple case: credit the depreciation expense account
		je.append(
			"accounts",
			{
				"account": depreciation_expense_account,
				"credit_in_account_currency": value_after_dep,
				"cost_center": cost_center,
				"reference_type": "Asset",
				"reference_name": asset_name,
			},
		)

	je.insert(ignore_permissions=True)
	je.submit()

	# ── Update Asset status ──
	update_fields = {
		"status": "Scrapped",
		"journal_entry_for_scrap": je.name,
		"disposal_date": scrapping_date,
	}

	if reason:
		update_fields["custom_reason_for_scrapping"] = reason

	frappe.db.set_value("Asset", asset_name, update_fields)
	# Retiring the animal is deliberately NOT done here. api/animal.retire_animal()
	# is the single writer of the final Animal.status, and it derives that status
	# from STATUS_BY_DISPOSAL_TYPE — a hardcoded 'Dead' here was wrong for
	# 'Condemned' and 'Slaughtered', which map to 'Culled'. It also sets `disabled`
	# and recomputes the herd headcount, neither of which happened here.
	#
	# No frappe.db.commit() either: committing mid-flow stranded the asset postings
	# when a later step failed, and defeated the rollback api/operations._run() and
	# LivestockDisposal.on_submit() depend on.

	return {
		"success": True,
		"asset": asset_name,
		"status": "Scrapped",
		"journal_entry": je.name,
		"reason": reason,
	}
