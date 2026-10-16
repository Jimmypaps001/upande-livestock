# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A straw the ledger has no stock or value for no longer stops a service, and the
stock list is the pickers' list.

The phone's Service stopped with "Valuation Rate for the Item Semen Delta Dolmen
is required to do accounting entries": the store showed 5 straws (a Bin row) but
the item has no stock ledger entry behind them, so availability (read off Bin)
passed and ERPNext then refused the whole service, "0 of 2 served". Nothing about
the cow was wrong. Availability now reads the ledger, so such a line is short and
its issue waits as a draft; and a line the ledger holds but cannot value is
allowed at zero value (ERPNext's own way out), while a valued line keeps its cost.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from upande_livestock.serverscripts.breeding.create_service_event import create_service_event
from upande_livestock.serverscripts.common import event_items as EI
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.mobile.get_livestock_stock import get_livestock_stock
from upande_livestock.serverscripts.tests.mapping_fixtures import MAPPED_SERVICE, pin_mapping
from upande_livestock.serverscripts.tests.test_operations import _employee, _make_cow, _purge, _purge_events_for


def _entry_with(*lines):
	se = frappe.new_doc("Stock Entry")
	se.company = frappe.db.get_single_value("Livestock Settings", "custom_default_company")
	for code, wh in lines:
		row = se.append("items", {})
		row.item_code, row.s_warehouse, row.qty = code, wh, 1
	return se


class TestAnUnvaluedLineIsAllowedAtZero(IntegrationTestCase):
	def test_a_line_with_no_rate_and_no_purchase_history_is_zero_valued_and_warned(self):
		se = _entry_with(("ZZ-ITEM", "ZZ-WH"))
		with patch("erpnext.stock.stock_ledger.get_valuation_rate", return_value=0), \
		     patch.object(livestock_stock, "last_purchase_rate", return_value=0):
			livestock_stock.allow_unvalued_lines(se)
		self.assertEqual(se.items[0].allow_zero_valuation_rate, 1)
		self.assertIn("has no cost", livestock_stock.warnings_made()[0])

	def test_a_line_with_a_rate_keeps_its_cost(self):
		se = _entry_with(("ZZ-ITEM", "ZZ-WH"))
		with patch("erpnext.stock.stock_ledger.get_valuation_rate", return_value=1150):
			livestock_stock.allow_unvalued_lines(se)
		self.assertFalse(se.items[0].allow_zero_valuation_rate)


class TestAServiceOnStockTheLedgerNeverHad(IntegrationTestCase):
	STRAW = "Semen Delta Dolmen"
	STORE = "Drug/ Medicine store- old office - KR"

	def setUp(self):
		have = frappe.db.get_value("Bin", {"item_code": self.STRAW, "warehouse": self.STORE}, "actual_qty")
		ledger = frappe.db.count("Stock Ledger Entry", {"item_code": self.STRAW, "is_cancelled": 0})
		if flt(have) < 1 or ledger:
			raise unittest.SkipTest("needs a straw held in a Bin with no ledger behind it")
		pin_mapping(self, MAPPED_SERVICE)
		self.cow = _make_cow("ZZ UNVALUED COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)

	def test_the_service_is_recorded_and_the_issue_waits_as_a_draft(self):
		res = create_service_event(
			{
				"animal": self.cow.name,
				"operator": _employee(),
				"service_type": "A.I.",
				"service_date": today(),
				"items": [{"item_code": self.STRAW, "qty": 1, "source_warehouse": self.STORE}],
			}
		)
		self.assertTrue(res.get("ok"), res)
		self.assertTrue(res.get("stock_entry"))
		self.addCleanup(self._drop_entry, res["stock_entry"])
		# The Bin says 5, the ledger holds none: short, so the service stands
		# and the issue is a named draft instead of a raw ERPNext refusal.
		self.assertEqual(frappe.db.get_value("Stock Entry", res["stock_entry"], "docstatus"), 0)
		self.assertEqual(res["stock_drafts"][0]["stock_entry_type"], "Livestock Service")

	def _drop_entry(self, name):
		_purge_events_for(self.cow.name)
		if frappe.db.get_value("Stock Entry", name, "docstatus") == 1:
			frappe.get_doc("Stock Entry", name).cancel()
		_purge("Stock Entry", name)


class TestTheStockList(IntegrationTestCase):
	def test_it_lists_only_mapped_groups_by_store_with_quantities(self):
		with patch.object(EI, "_rules", return_value={"Service": {"posts": True, "groups": ["Dairy Semen"], "default_store": None, "must_name_item": False}}), \
		     patch.object(EI, "_company_warehouses", return_value=["Drug/ Medicine store- old office - KR"]), \
		     patch.object(EI, "_balances", return_value=[
			     {"name": "S1", "item_name": "Straw One", "stock_uom": "Nos", "item_group": "Dairy Semen",
			      "warehouse": "Drug/ Medicine store- old office - KR", "qty": 4},
		     ]) as bal:
			stores = EI.stock_overview()
		bal.assert_called_once()
		self.assertEqual(bal.call_args[0][0], ["Dairy Semen"])
		self.assertEqual(stores[0]["warehouse"], "Drug/ Medicine store- old office - KR")
		item = stores[0]["items"][0]
		self.assertEqual((item["item_code"], item["qty"], item["uom"], item["events"]), ("S1", 4.0, "Nos", ["Service"]))

	def test_the_endpoint_answers_with_a_time_and_is_guarded(self):
		out = get_livestock_stock()
		self.assertTrue(out.get("ok"), out)
		self.assertIn("as_of", out)
		self.assertEqual(out["count"], sum(len(s["items"]) for s in out["stores"]))
		with patch("upande_livestock.serverscripts.mobile.get_livestock_stock.guard_read",
		           side_effect=frappe.PermissionError("no")):
			self.assertIn("error", get_livestock_stock())
