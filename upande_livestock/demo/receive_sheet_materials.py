# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Receive the raw materials the August 2026 formulations need but the store lacks.

WHY THIS EXISTS. The site's concentrate recipes had substituted Cotton Seed Cake
for the sheet's wheat bran and rapeseed/canola. Moving the recipes onto the sheet
therefore makes three inputs short at once, not one:

    Canola Meal     3,250.8 kg/week needed, 0 on hand — never received here at all
    Wheat Bran      3,137.9 kg/week needed, 46.7 on hand
    Soya Meal         149.0 kg/week needed, 0 on hand

Two TMR inputs are short for the same reason a demo site usually is — the feed
was eaten and never restocked — and without them no herd can be fed at all:

    Silage          6,107 kg/day needed across five herds, 183 on hand
    Milk Replacer       9 kg/day needed by the two calf herds, 0 on hand

Without a valuation rate ERPNext refuses the Manufacture entry outright —
"Valuation Rate for the Item ... is required to do accounting entries" — so a
Work Order for the lactating concentrate cannot post no matter how correct the
BOM is.

Rates are the sheet's own unit prices, so the manufactured cost per kg lands
where the sheet says it should. Quantities default to two weeks of the sheet's
consumption, rounded up, which is enough to mix a week and still hold cover.

Development and training sites only: this posts a real Material Receipt.

    bench --site <site> execute upande_livestock.demo.receive_sheet_materials.run
    bench --site <site> execute upande_livestock.demo.receive_sheet_materials.apply_now
"""

import frappe
from frappe.utils import add_days, flt, today

# item code -> (label, sheet unit price, kg to receive)
# The kg figures are two weeks of the sheet's weekly consumption, rounded up to
# something a store would actually order.
MATERIALS = {
	# Concentrate ingredients the sheet's formulas need.
	"4040010026": ("Canola Meal (sheet: Rapeseed/Canola)", 52.0, 7000.0),
	"4040010020": ("Wheat Bran", 27.0, 7000.0),
	"4040010037": ("Soya Meal (sheet: Soyabean meal)", 100.0, 500.0),
	# TMR inputs. Silage is farm-produced and the site carries one item where
	# the sheet prices sorghum at 7.20 and maize at 10.00; 8.65 is those two
	# weighted by the quantities the sheet itself feeds (2,503 kg sorghum against
	# 2,705 kg maize a day), so the ration costs what the sheet says it does.
	"4040010082": ("Silage - Farm Produced (sorghum/maize blended)", 8.65, 90000.0),
	"4040010095": ("Dehues Milk Replacer", 54.0, 200.0),
}

# The sheet's formulas draw raw materials from the raw-material store; the
# concentrate lands in the concentrate store and the TMR in the WIP store.
RAW_STORE = "Feed Store - Raw materials - KR"


def _company():
	return frappe.db.get_single_value("Livestock Settings", "custom_default_company")


def _on_hand(item):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": RAW_STORE}, "actual_qty"))


def run(apply=False):
	apply_ = bool(apply)
	print("MODE:", "APPLY" if apply_ else "dry run")
	if not frappe.db.exists("Warehouse", RAW_STORE):
		print(f"  ! {RAW_STORE} is not a warehouse on this site")
		return

	rows = []
	print("\n{:<44}{:>10}{:>10}{:>12}".format("MATERIAL", "on hand", "receive", "rate"))
	for code, (label, rate, qty) in MATERIALS.items():
		if not frappe.db.exists("Item", code):
			print(f"  ! {label} ({code}) is not on this site")
			continue
		print(f"{label[:44]:<44}{_on_hand(code):>10.1f}{qty:>10.0f}{rate:>12.2f}")
		rows.append((code, qty, rate))
	if not rows:
		print("  nothing to receive")
		return
	if not apply_:
		print(f"\n  ~ would post one Material Receipt into {RAW_STORE}")
		return

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.purpose = "Material Receipt"
	se.company = _company()
	se.set_posting_time = 1
	# Back-dated a week so a Work Order posted today draws on stock that already
	# existed on its posting date. Stock received "now" is not available to an
	# entry timestamped a minute earlier.
	se.posting_date = add_days(today(), -7)
	se.remarks = "Opening stock for the August 2026 formulations (demo/receive_sheet_materials.py)"
	for code, qty, rate in rows:
		se.append("items", {
			"item_code": code,
			"qty": qty,
			"t_warehouse": RAW_STORE,
			"basic_rate": rate,
			"allow_zero_valuation_rate": 0,
		})
	se.insert(ignore_permissions=True)
	se.submit()
	frappe.db.commit()
	print(f"\n  + received via {se.name}")
	for code, (label, _r, _q) in MATERIALS.items():
		if frappe.db.exists("Item", code):
			print(f"     {label[:44]:<44}{_on_hand(code):>10.1f} on hand")


def apply_now():
	"""Zero-argument entry point — bench execute only imports on the no-arg path."""
	return run(apply=True)
