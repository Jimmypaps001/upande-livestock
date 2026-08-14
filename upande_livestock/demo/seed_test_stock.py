# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Create a Livestock Drug Store and stock it, so the stock-consuming flows can be
exercised end to end.

TEST SITES ONLY. This posts real Stock Entries and creates Items and a Warehouse.
It is deliberately NOT a patch and NOT a fixture — nothing here should fire on
someone's production migrate. Run it by hand:

    bench --site <site> execute upande_livestock.demo.seed_test_stock.run

Idempotent: every step checks for what it is about to create, so re-running tops up
nothing and duplicates nothing. Re-running after the stock is consumed does not
top it back up — pass `receive=True` explicitly for that, or call
`receive_stock()` on its own.

Why a dedicated store rather than reusing "Drug/ Medicine store- old office - KR"
(where the 8 real semen straws already sit): a test flow that draws down a real
store's balances is indistinguishable from a stores error later. A purpose-named
warehouse keeps demo movements separable from real ones.
"""

import frappe
from frappe.utils import flt, today

WAREHOUSE_NAME = "Livestock Drug Store"

# Realistic Kenyan-dairy vaccines, dewormers and treatment antibiotics. Item codes
# are prefixed so demo stock is obvious in a stock report.
DRUG_ITEMS = [
	# (item_code, item_name, stock_uom, opening_qty, rate)
	("LSK-VAC-FMD", "FMD Vaccine (50 dose vial)", "Nos", 20, 3500),
	("LSK-VAC-LSD", "Lumpy Skin Disease Vaccine (25 dose)", "Nos", 15, 2800),
	("LSK-VAC-ANTH", "Anthrax / Blackquarter Vaccine (100 dose)", "Nos", 10, 1900),
	("LSK-VAC-RVF", "Rift Valley Fever Vaccine (50 dose)", "Nos", 8, 4200),
	("LSK-DEW-ALB", "Albendazole 10% Oral Drench (1 L)", "Litre", 25, 1200),
	("LSK-DEW-IVE", "Ivermectin 1% Injectable (500 ml)", "Nos", 18, 2400),
	("LSK-DEW-LEV", "Levamisole 7.5% Injectable (100 ml)", "Nos", 12, 850),
	("LSK-AB-PENSTREP", "Penicillin-Streptomycin Injectable (100 ml)", "Nos", 30, 950),
	("LSK-AB-OTC", "Oxytetracycline LA 20% (100 ml)", "Nos", 24, 1100),
	("LSK-AB-INTRAMAM", "Intramammary Antibiotic Tube", "Nos", 60, 320),
	("LSK-SUP-CALCIUM", "Calcium Borogluconate 40% (400 ml)", "Nos", 20, 700),
	("LSK-SEMEN-TEST", "Semen Straw - Test Sire", "Nos", 40, 2500),
]

DRUG_ITEM_GROUP = "DRUGS"
SEMEN_ITEM_CODE = "LSK-SEMEN-TEST"


def _company():
	company = (
		frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or frappe.db.get_value("Company", {}, "name")
	)
	if not company:
		frappe.throw("No Company on this site — cannot seed livestock stock.")
	return company


def ensure_warehouse(company):
	"""Create (or find) the Livestock Drug Store for `company`.

	Frappe appends " - <abbr>" to a warehouse name, so the stored name is
	"Livestock Drug Store - KR" for Karen Roses. We look that up rather than
	assuming, so this works on a site with a different company abbreviation.
	"""
	abbr = frappe.db.get_value("Company", company, "abbr")
	full_name = f"{WAREHOUSE_NAME} - {abbr}"
	if frappe.db.exists("Warehouse", full_name):
		return full_name

	parent = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "warehouse_name": "All Warehouses"}, "name"
	) or frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name")

	payload = {
		"doctype": "Warehouse",
		"warehouse_name": WAREHOUSE_NAME,
		"company": company,
		"parent_warehouse": parent,
		"is_group": 0,
	}

	# This bench carries a mandatory `custom_farm` custom field on Warehouse. It is
	# site-specific, so it is discovered rather than assumed: any mandatory Link
	# custom field is filled with the value most of that company's other warehouses
	# use, which keeps the demo store in the same farm as the real drug store.
	for field in frappe.get_all(
		"Custom Field",
		filters={"dt": "Warehouse", "reqd": 1, "fieldtype": "Link"},
		fields=["fieldname", "options"],
	):
		if payload.get(field.fieldname):
			continue
		common = frappe.db.sql(
			f"""SELECT `{field.fieldname}` AS value FROM `tabWarehouse`
			    WHERE company = %s AND IFNULL(`{field.fieldname}`, '') != ''
			    GROUP BY `{field.fieldname}` ORDER BY COUNT(*) DESC LIMIT 1""",
			(company,),
		)
		value = common[0][0] if common else frappe.db.get_value(field.options, {}, "name")
		if value:
			payload[field.fieldname] = value
			print(f"  {field.fieldname} (mandatory on this site) = {value}")

	doc = frappe.get_doc(payload).insert(ignore_permissions=True)
	print(f"  created Warehouse {doc.name}")
	return doc.name


def ensure_items():
	created = []
	for code, name, uom, _qty, _rate in DRUG_ITEMS:
		if frappe.db.exists("Item", code):
			continue
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": DRUG_ITEM_GROUP,
				"stock_uom": uom,
				"is_stock_item": 1,
				"is_purchase_item": 1,
				"is_sales_item": 0,
				"include_item_in_manufacturing": 0,
				"description": f"{name} — livestock demo stock seeded by demo/seed_test_stock.py.",
			}
		).insert(ignore_permissions=True)
		created.append(code)
	if created:
		print(f"  created {len(created)} Item(s): {', '.join(created)}")
	return [row[0] for row in DRUG_ITEMS]


def receive_stock(warehouse, company):
	"""Material Receipt the opening quantities into `warehouse`.

	Only items with no balance in this warehouse are received, so re-running does
	not keep piling stock in. Rate is set explicitly — a Material Receipt of an item
	with no valuation history is rejected without one.
	"""
	rows = []
	for code, _name, _uom, qty, rate in DRUG_ITEMS:
		on_hand = flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouse}, "actual_qty"))
		if on_hand > 0:
			continue
		rows.append((code, qty, rate))

	if not rows:
		print("  every seeded item already has stock in this warehouse — nothing received")
		return None

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.purpose = "Material Receipt"
	se.company = company
	se.set_posting_time = 1
	se.posting_date = today()
	se.remarks = "Livestock demo opening stock (demo/seed_test_stock.py)"
	for code, qty, rate in rows:
		item = se.append("items", {})
		item.item_code = code
		item.qty = qty
		item.t_warehouse = warehouse
		item.basic_rate = rate
		item.allow_zero_valuation_rate = 0
	se.insert(ignore_permissions=True)
	se.submit()
	print(f"  received {len(rows)} item(s) into {warehouse} via {se.name}")
	return se.name


def configure_settings(warehouse, company):
	"""Point Livestock Settings at the seeded store.

	These are the settings the drug and semen issues read
	(livestock_stock.drug_warehouse / semen_warehouse / default_semen_item). Without
	them every issue fails with "No source warehouse".
	"""
	updates = {
		"drug_warehouse": warehouse,
		"semen_warehouse": warehouse,
		"semen_item": SEMEN_ITEM_CODE,
	}
	if not frappe.db.get_single_value("Livestock Settings", "custom_default_company"):
		updates["custom_default_company"] = company
	for field, value in updates.items():
		frappe.db.set_single_value("Livestock Settings", field, value)
	print(f"  Livestock Settings: {', '.join(f'{k}={v}' for k, v in updates.items())}")


def run(receive=True):
	company = _company()
	print(f"Seeding livestock demo stock for company: {company}")
	warehouse = ensure_warehouse(company)
	ensure_items()
	if receive:
		receive_stock(warehouse, company)
	configure_settings(warehouse, company)
	frappe.db.commit()
	print("Done.")
	return {"warehouse": warehouse, "company": company}
