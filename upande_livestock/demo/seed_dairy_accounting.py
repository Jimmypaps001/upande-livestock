# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Wire up the dairy side so milking, drugs and feeding post real accounting.

Creates the milk item, the Dairy 1 and feed warehouses, the inventory and expense
accounts, and sets those accounts at BOTH the Item and the Item Group level —
Frappe 16 resolves an item's accounts from Item Defaults first and falls back to the
Item Group's defaults, so a value present in only one place leaves half the paths
unresolved.

TEST/SETUP SITES. Run by hand:

    bench --site <site> execute upande_livestock.demo.seed_dairy_accounting.run

Idempotent throughout. Parent accounts and warehouse groups are discovered from the
company's existing chart rather than hardcoded, so this works on a site whose chart
differs.

Milking is a Material Receipt: milk is produced by the herd and received into a
store, so the Stock Entry carries a target warehouse and NO source warehouse. The
"Milking" Stock Entry Type already has purpose "Material Receipt" (see
install.ensure_milking_stock_entry_type) — if a source warehouse ever appears to be
required, the entry type's purpose is what to check first, because a Material
Transfer purpose demands both ends.
"""

import frappe
from frappe.utils import flt

MILK_ITEM_CODE = "WDL-RAW-MILK"
MILK_ITEM_NAME = "Westwood Dairies Raw Milk"
MILK_UOM = "Kilogram"  # Milk Recording measures yield in kg (net_yield_kg)
# Standard cost per kg used to value milk into stock. Milk has no purchase price —
# it is produced by the herd — and a Material Receipt with no valuation is rejected
# outright ("Valuation Rate for the Item ... is required"), which silently cost the
# whole Stock Entry before this was set. Deliberately below a typical selling price
# so the revenue JE still shows a margin.
MILK_VALUATION_RATE = 45.0

DAIRY_WAREHOUSE = "Dairy 1"
FEED_WAREHOUSE = "Livestock Feed Store"
DRUG_WAREHOUSE = "Livestock Drug Store"

DAIRY_ITEM_GROUP = "DAIRY"
DRUG_ITEM_GROUP = "DRUGS"

# label -> (account_name, root_type, account_type, preferred parent name fragments)
#
# The parent preferences matter more than they look. An earlier version of this
# script picked "the parent of an existing account with the same account_type", and
# on this chart that found `Directors current account`, an Expense-Account-typed leaf
# sitting under `Other creditors` — so the new expense accounts were created under a
# liability group and Frappe silently rewrote their root_type to Liability. Drug costs
# would have posted to a liability. Parents are now matched on root_type and name,
# and the root_type of what we created is verified afterwards.
ACCOUNTS = {
	"milk_stock": ("Livestock Milk Stock", "Asset", "Stock", ["Stock Assets", "Current Assets"]),
	"drug_stock": ("Livestock Drug Stock", "Asset", "Stock", ["Stock Assets", "Current Assets"]),
	"feed_stock": ("Livestock Feed Stock", "Asset", "Stock", ["Stock Assets", "Current Assets"]),
	"drug_expense": (
		"Livestock Drug Expense",
		"Expense",
		"Expense Account",
		["Dairy Expense", "Direct Expense", "EXPENSES"],
	),
	"feed_expense": (
		"Livestock Feed Expense",
		"Expense",
		"Expense Account",
		["Dairy Feed", "Dairy Expense", "Direct Expense", "EXPENSES"],
	),
	"milk_income": (
		"Livestock Milk Income",
		"Income",
		"Income Account",
		["Dairy Income", "INCOME"],
	),
	# Debit side of the milk revenue JE: milk delivered but not yet invoiced.
	# Deliberately NOT account_type "Receivable" — Frappe requires a party on every
	# Receivable line and a Milk Recording has no customer, so a receivable here made
	# the JE fail with "Party is mandatory" and that failure was only logged, never
	# shown. An untyped Asset account carries no party requirement.
	"milk_unbilled": (
		"Livestock Milk Unbilled",
		"Asset",
		"",
		["Current Assets", "Stock Assets"],
	),
}


def _company():
	company = (
		frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or frappe.db.get_value("Company", {}, "name")
	)
	if not company:
		frappe.throw("No Company on this site.")
	return company


def _abbr(company):
	return frappe.db.get_value("Company", company, "abbr")


def _parent_for(company, root_type, preferences):
	"""A group account of `root_type` to hang a new account under.

	Only groups whose own root_type matches are ever considered, so the created
	account cannot have its root_type silently rewritten by its parent. `preferences`
	is tried in order as name fragments, then any group of the right root_type.
	"""
	# Exact account_name first, then substring. A bare substring search is not enough:
	# "Current Assets" is a substring of "Non Current Assets", and matching that put
	# unbilled milk under non-current assets. account_name excludes the numeric prefix
	# and the company suffix, so an exact compare on it is meaningful.
	# Preference order is the OUTER loop: a later, broader fragment must never beat an
	# earlier, more specific one. (With the loops the other way round, an exact match
	# on "EXPENSES" won over a substring match on "Dairy Expense" and pulled the drug
	# account up to the expense root.) Within one fragment, exact beats substring so
	# "Current Assets" cannot resolve to "Non Current Assets".
	for fragment in preferences:
		for account_name in (fragment, ["like", f"%{fragment}%"]):
			match = frappe.db.get_value(
				"Account",
				{
					"company": company,
					"is_group": 1,
					"root_type": root_type,
					"account_name": account_name,
				},
				"name",
			)
			if match:
				return match
	return frappe.db.get_value("Account", {"company": company, "is_group": 1, "root_type": root_type}, "name")


def ensure_accounts(company):
	"""Create the six livestock accounts, returning {label: account name}.

	Self-healing: an account that already exists but whose root_type does not match
	what it is for is reparented. That is not hypothetical — the first run of this
	script created both expense accounts under a liability group.
	"""
	out = {}
	for label, (account_name, root_type, account_type, preferences) in ACCOUNTS.items():
		full = f"{account_name} - {_abbr(company)}"
		if frappe.db.exists("Account", full):
			out[label] = full
			actual_root, actual_parent = frappe.db.get_value("Account", full, ["root_type", "parent_account"])
			preferred = _parent_for(company, root_type, preferences)
			# The script's resolved parent is authoritative — compared directly rather
			# than fuzzily, because fuzzy matching is what let "Current Assets" pass for
			# "Non Current Assets". Re-running therefore re-asserts this layout, which is
			# the point of a setup script.
			if actual_root != root_type or (preferred and actual_parent != preferred):
				doc = frappe.get_doc("Account", full)
				doc.parent_account = preferred
				doc.root_type = root_type
				doc.account_type = account_type
				doc.flags.ignore_permissions = True
				doc.save(ignore_permissions=True)
				print(
					f"  REPAIRED {full}: root_type {actual_root} -> {root_type}, "
					f"parent {actual_parent} -> {preferred}"
				)
			continue
		parent = _parent_for(company, root_type, preferences)
		if not parent:
			frappe.throw(f"No parent group found for a {root_type} account in {company}.")
		doc = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": account_name,
				"company": company,
				"parent_account": parent,
				"root_type": root_type,
				"account_type": account_type,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		# Frappe rewrites root_type to match the parent; make sure it did not.
		if frappe.db.get_value("Account", doc.name, "root_type") != root_type:
			frappe.throw(
				f"{doc.name} was created under {parent} but its root_type is not {root_type}. "
				"Fix the parent group before re-running."
			)
		out[label] = doc.name
		print(f"  created Account {doc.name}  (under {parent})")
	return out


def _ensure_warehouse(company, warehouse_name, account=None):
	abbr = _abbr(company)
	full = f"{warehouse_name} - {abbr}"
	if frappe.db.exists("Warehouse", full):
		if account and not frappe.db.get_value("Warehouse", full, "account"):
			frappe.db.set_value("Warehouse", full, "account", account)
			print(f"  set {full}.account = {account}")
		return full

	parent = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "warehouse_name": "All Warehouses"}, "name"
	) or frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name")

	payload = {
		"doctype": "Warehouse",
		"warehouse_name": warehouse_name,
		"company": company,
		"parent_warehouse": parent,
		"is_group": 0,
	}
	if account:
		payload["account"] = account

	# This bench has a mandatory `custom_farm` on Warehouse; discover any such field
	# rather than assuming which one (see demo/seed_test_stock.py).
	for field in frappe.get_all(
		"Custom Field",
		filters={"dt": "Warehouse", "reqd": 1, "fieldtype": "Link"},
		fields=["fieldname", "options"],
	):
		if payload.get(field.fieldname):
			continue
		common = frappe.db.sql(
			f"""SELECT `{field.fieldname}` FROM `tabWarehouse`
			    WHERE company = %s AND IFNULL(`{field.fieldname}`, '') != ''
			    GROUP BY `{field.fieldname}` ORDER BY COUNT(*) DESC LIMIT 1""",
			(company,),
		)
		value = common[0][0] if common else frappe.db.get_value(field.options, {}, "name")
		if value:
			payload[field.fieldname] = value

	doc = frappe.get_doc(payload).insert(ignore_permissions=True)
	print(f"  created Warehouse {doc.name}" + (f" (account {account})" if account else ""))
	return doc.name


def ensure_warehouses(company, accounts):
	return {
		"dairy": _ensure_warehouse(company, DAIRY_WAREHOUSE, accounts["milk_stock"]),
		"feed": _ensure_warehouse(company, FEED_WAREHOUSE, accounts["feed_stock"]),
		"drug": _ensure_warehouse(company, DRUG_WAREHOUSE, accounts["drug_stock"]),
	}


def _set_item_defaults(parent_doctype, parent_name, company, **values):
	"""Upsert the Item Default row for `company` on an Item or Item Group.

	Frappe 16 reads an item's accounts from its own Item Defaults and falls back to
	the Item Group's, so both levels are populated. Only blank fields are filled —
	an existing deliberate value is never overwritten.
	"""
	doc = frappe.get_doc(parent_doctype, parent_name)
	table = "item_defaults" if parent_doctype == "Item" else "item_group_defaults"
	row = next((r for r in doc.get(table) or [] if r.company == company), None)
	if not row:
		row = doc.append(table, {"company": company})
	changed = []
	for field, value in values.items():
		if value and not row.get(field):
			row.set(field, value)
			changed.append(field)
	if changed or row.is_new():
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
		print(f"  {parent_doctype} {parent_name}: set {', '.join(changed) or 'company row'}")


def ensure_milk_item(company, warehouses, accounts):
	if not frappe.db.exists("Item", MILK_ITEM_CODE):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": MILK_ITEM_CODE,
				"item_name": MILK_ITEM_NAME,
				"item_group": DAIRY_ITEM_GROUP,
				"stock_uom": MILK_UOM,
				"is_stock_item": 1,
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"include_item_in_manufacturing": 0,
				"description": f"{MILK_ITEM_NAME} — raw milk received from the herd at each milking.",
				"valuation_rate": MILK_VALUATION_RATE,
			}
		).insert(ignore_permissions=True)
		print(
			f"  created Item {MILK_ITEM_CODE} ({MILK_ITEM_NAME}, {MILK_UOM}, valuation {MILK_VALUATION_RATE})"
		)
	elif not flt(frappe.db.get_value("Item", MILK_ITEM_CODE, "valuation_rate")):
		frappe.db.set_value("Item", MILK_ITEM_CODE, "valuation_rate", MILK_VALUATION_RATE)
		print(f"  set {MILK_ITEM_CODE}.valuation_rate = {MILK_VALUATION_RATE}")

	_set_item_defaults(
		"Item",
		MILK_ITEM_CODE,
		company,
		default_warehouse=warehouses["dairy"],
		income_account=accounts["milk_income"],
		expense_account=accounts["feed_expense"],
	)
	return MILK_ITEM_CODE


def ensure_item_group_defaults(company, warehouses, accounts):
	"""Set group-level defaults for DAIRY and DRUGS.

	This is the half the user asked for explicitly: Frappe 16 falls back to the Item
	Group when an item has no default of its own, so every drug in the 595-item DRUGS
	group gets the drug expense account without being touched one by one.
	"""
	_set_item_defaults(
		"Item Group",
		DAIRY_ITEM_GROUP,
		company,
		default_warehouse=warehouses["dairy"],
		income_account=accounts["milk_income"],
		expense_account=accounts["feed_expense"],
	)
	_set_item_defaults(
		"Item Group",
		DRUG_ITEM_GROUP,
		company,
		default_warehouse=warehouses["drug"],
		expense_account=accounts["drug_expense"],
	)


def configure_settings(company, milk_item, warehouses, accounts):
	updates = {
		"custom_default_company": company,
		"custom_milk_item": milk_item,
		"custom_milk_target_warehouse": warehouses["dairy"],
		"custom_milk_discard_warehouse": warehouses["dairy"],
		"custom_feed_wip_warehouse": warehouses["feed"],
		"drug_warehouse": warehouses["drug"],
		"semen_warehouse": warehouses["drug"],
		# Despite its name, custom_default_credit_account is the account the milk
		# revenue JE DEBITS (milk_recording.py: dr.account = credit_acct), so it must
		# be the asset side — the company's receivable. Pointing it at the income
		# account would debit and credit the same account and net to nothing.
		"custom_default_credit_account": accounts["milk_unbilled"],
	}
	for field, value in updates.items():
		frappe.db.set_single_value("Livestock Settings", field, value)
	print("  Livestock Settings updated:")
	for k, v in updates.items():
		print(f"    {k} = {v}")


def verify(company, milk_item, warehouses, accounts):
	"""Report what a stock/GL posting would resolve to, so gaps are visible now."""
	print("\nResolution check:")
	item_row = frappe.db.get_value(
		"Item Default",
		{"parent": milk_item, "parenttype": "Item", "company": company},
		["default_warehouse", "income_account", "expense_account"],
		as_dict=True,
	)
	print(f"  Item {milk_item} defaults: {item_row}")
	for group in (DAIRY_ITEM_GROUP, DRUG_ITEM_GROUP):
		grp = frappe.db.get_value(
			"Item Default",
			{"parent": group, "parenttype": "Item Group", "company": company},
			["default_warehouse", "income_account", "expense_account"],
			as_dict=True,
		)
		print(f"  Item Group {group} defaults: {grp}")
	for label, wh in warehouses.items():
		print(f"  Warehouse {wh}: account = {frappe.db.get_value('Warehouse', wh, 'account')}")
	se_type = frappe.db.get_value("Stock Entry Type", "Milking", "purpose")
	print(f"  Stock Entry Type 'Milking' purpose = {se_type} (must be Material Receipt)")


def run():
	company = _company()
	print(f"Configuring dairy accounting for: {company}")
	accounts = ensure_accounts(company)
	warehouses = ensure_warehouses(company, accounts)
	milk_item = ensure_milk_item(company, warehouses, accounts)
	ensure_item_group_defaults(company, warehouses, accounts)
	configure_settings(company, milk_item, warehouses, accounts)
	frappe.db.commit()
	verify(company, milk_item, warehouses, accounts)
	print("\nDone.")
	return {
		"company": company,
		"milk_item": milk_item,
		"warehouses": warehouses,
		"accounts": accounts,
	}
