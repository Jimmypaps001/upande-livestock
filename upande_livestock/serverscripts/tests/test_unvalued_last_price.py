# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Stock the ledger holds at no value is costed at its last purchase price.

An item with a count but no cost used to issue at zero, which hid what the
round cost the farm. It now takes Item.last_purchase_rate, then the latest
submitted Purchase Receipt / Invoice rate. Only an item never bought at all
is issued at zero, and then the answer carries a warning.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.tests.test_operations import _employee, _purge

ITEM = "ZZ-LPP-DRUG"


def _company():
	return frappe.db.get_single_value("Livestock Settings", "custom_default_company")


def _warehouses(company, n=2):
	return frappe.get_all("Warehouse", filters={"company": company, "is_group": 0, "disabled": 0}, pluck="name", limit=n)


class TestUnvaluedStockUsesLastPurchasePrice(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = _company()
		self.wh, self.other = _warehouses(self.company)
		self.docs = []
		self.addCleanup(self._clean)
		self._clean()
		group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		frappe.get_doc(
			{"doctype": "Item", "item_code": ITEM, "item_name": "ZZ LPP Drug", "item_group": group,
			 "stock_uom": "Nos", "is_stock_item": 1, "last_purchase_rate": 0}
		).insert(ignore_permissions=True)
		# Held in the ledger, at no value.
		receipt = frappe.get_doc(
			{"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
			 "company": self.company,
			 "items": [{"item_code": ITEM, "qty": 10, "t_warehouse": self.wh, "basic_rate": 0,
			            "allow_zero_valuation_rate": 1}]}
		).insert(ignore_permissions=True)
		receipt.submit()
		self.docs.append(("Stock Entry", receipt.name))
		livestock_stock.warnings_made()

	def _clean(self):
		for dt, name in reversed(getattr(self, "docs", [])):
			_purge(dt, name)
		for dt in ("Stock Entry", "Purchase Receipt"):
			for parent in frappe.get_all(dt + " Item" if dt != "Stock Entry" else "Stock Entry Detail",
			                             filters={"item_code": ITEM}, pluck="parent"):
				_purge(dt, parent)
		if frappe.db.exists("Item", ITEM):
			try:
				frappe.delete_doc("Item", ITEM, force=True, ignore_permissions=True)
			except Exception:
				pass
		frappe.db.commit()

	def _issue(self):
		name = livestock_stock.issue_items(
			[{"item_code": ITEM, "qty": 2, "warehouse": self.wh}],
			remarks="test", employee=_employee(), what="Deworming",
		)
		self.docs.append(("Stock Entry", name))
		return frappe.get_doc("Stock Entry", name)

	def test_item_last_purchase_rate_is_used(self):
		frappe.db.set_value("Item", ITEM, "last_purchase_rate", 40)
		se = self._issue()
		self.assertEqual(flt(se.items[0].basic_rate), 40)
		self.assertEqual(flt(se.items[0].basic_amount), 80)
		self.assertFalse(se.items[0].allow_zero_valuation_rate)
		self.assertEqual(livestock_stock.warnings_made(), [])

	def test_the_latest_purchase_receipt_rate_is_used(self):
		supplier = frappe.db.get_value("Supplier", {}, "name")
		if not supplier:
			self.skipTest("needs a supplier")
		pr = frappe.get_doc(
			{"doctype": "Purchase Receipt", "supplier": supplier, "company": self.company,
			 "posting_date": today(), "set_posting_time": 1, "letter_head": None,
			 "items": [{"item_code": ITEM, "qty": 5, "rate": 25, "warehouse": self.other}]}
		).insert(ignore_permissions=True)
		pr.flags.ignore_links = True
		pr.submit()
		self.docs.append(("Purchase Receipt", pr.name))
		frappe.db.set_value("Item", ITEM, "last_purchase_rate", 0)
		self.assertEqual(livestock_stock.last_purchase_rate(ITEM, self.company), 25)
		se = self._issue()
		self.assertEqual(flt(se.items[0].basic_rate), 25)
		self.assertFalse(se.items[0].allow_zero_valuation_rate)

	def test_no_history_issues_at_zero_and_warns(self):
		se = self._issue()
		self.assertEqual(flt(se.items[0].basic_rate), 0)
		warnings = livestock_stock.warnings_made()
		self.assertEqual(len(warnings), 1)
		self.assertIn("has no cost", warnings[0])
		self.assertIn("ZZ LPP Drug", warnings[0])
