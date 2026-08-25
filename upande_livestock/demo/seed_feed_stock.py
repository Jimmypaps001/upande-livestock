# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Give the feed items a stock ledger, so the feeding programme can post.

A site restored from a partial backup can carry `Bin` quantities without the
Stock Ledger Entries behind them. ERPNext values from the ledger, not from Bin,
so every feed item prices at zero and the Manufacture entry is refused — and a
transfer that the availability check cleared then fails on negative stock,
because the ledger balance is 0 while Bin reads 88.70.

This lays down one Stock Reconciliation that restates each feed item at the
quantity it already holds, with a real rate. Quantities do not change; only the
ledger is seeded. Rates come from Bin, then the item's own BOM cost, then the
Item master.

    bench --site <site> execute upande_livestock.demo.seed_feed_stock.run

Development and training sites only. It posts a real accounting document.
"""

import frappe
from frappe.utils import flt, nowtime, today

EXPENSE_ACCOUNT = "Stock Adjustment"


def _feed_items():
	"""Every item reachable from a herd's BOM, through sub-assemblies."""
	seen, items, queue = set(), set(), []
	for bom in frappe.get_all("Herds", filters=[["bom", "is", "set"]], pluck="bom"):
		queue.append(bom)
	while queue:
		bom = queue.pop()
		if not bom or bom in seen:
			continue
		seen.add(bom)
		items.add(frappe.db.get_value("BOM", bom, "item"))
		for row in frappe.get_all("BOM Item", filters={"parent": bom}, fields=["item_code", "bom_no"]):
			items.add(row.item_code)
			sub = row.bom_no or frappe.db.get_value("Item", row.item_code, "default_bom")
			if sub:
				queue.append(sub)
	return sorted(i for i in items if i)


def _rate(item, bin_rate):
	if flt(bin_rate) > 0.01:
		return flt(bin_rate)
	bom = frappe.db.get_value("Item", item, "default_bom")
	if bom:
		qty, cost = frappe.db.get_value("BOM", bom, ["quantity", "total_cost"])
		if flt(qty) and flt(cost):
			return flt(cost) / flt(qty)
	return flt(frappe.db.get_value("Item", item, "valuation_rate")) or 1.0


def run(company=None):
	company = company or frappe.db.get_single_value("Livestock Settings", "custom_default_company")
	if not company:
		frappe.throw("Set Livestock Settings → Default Company first.")
	abbr = frappe.db.get_value("Company", company, "abbr")

	items = _feed_items()
	rows = frappe.get_all(
		"Bin",
		filters=[["item_code", "in", items], ["actual_qty", ">", 0]],
		fields=["item_code", "warehouse", "actual_qty", "valuation_rate"],
	)
	if not rows:
		print("nothing to seed — no positive balances for {} feed items".format(len(items)))
		return

	sr = frappe.new_doc("Stock Reconciliation")
	sr.company = company
	sr.purpose = "Stock Reconciliation"
	sr.posting_date = today()
	sr.posting_time = nowtime()
	sr.set_posting_time = 1
	sr.expense_account = "{0} - {1}".format(EXPENSE_ACCOUNT, abbr)
	for r in rows:
		sr.append(
			"items",
			{
				"item_code": r.item_code,
				"warehouse": r.warehouse,
				"qty": flt(r.actual_qty),
				"valuation_rate": _rate(r.item_code, r.valuation_rate),
			},
		)
	sr.insert(ignore_permissions=True)
	sr.submit()
	frappe.db.commit()
	print("seeded {} balances across {} feed items — {}".format(len(rows), len(items), sr.name))
	return sr.name
