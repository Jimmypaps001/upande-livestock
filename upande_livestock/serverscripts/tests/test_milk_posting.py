# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where a milk recording's postings land, and what cancelling one undoes.

A recording names its company, but posting read Livestock Settings' default
company instead, so the live site's milk — entered under Kaitet Group and
Westwood Dairies — was posted as Karen Roses'. And a recording had no
on_cancel, so cancelling one left its milk in stock and its revenue booked.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_livestock.serverscripts.milking.create_milk_recording import create_milk_recording
from upande_livestock.serverscripts.tests.test_milking import _purge

MARKER = "TEST-MILKPOST"


class TestMilkPosting(IntegrationTestCase):
	def setUp(self):
		self.herd = frappe.db.get_value("Herds", {"custom_is_milking": 1}, "name")
		self.company = frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		self.warehouse = frappe.db.get_single_value("Livestock Settings", "custom_milk_target_warehouse")
		if not (self.herd and self.company and self.warehouse):
			self.skipTest("this site has no milking herd or milk settings")
		_purge(MARKER)
		self.addCleanup(_purge, MARKER)

	def _record(self, **extra):
		got = create_milk_recording({
			"herd": self.herd,
			"recording_date": today(),
			"total_yield_kg": 12.0,
			"price_per_kg": 50,
			"remarks": MARKER,
			**extra,
		})
		self.assertTrue(got.get("ok"), got.get("error"))
		return frappe.get_doc("Milk Recording", got["name"])

	def test_the_milk_posts_under_the_recordings_company(self):
		doc = self._record(company=self.company)
		self.assertTrue(doc.stock_entry, "no stock was posted")
		self.assertEqual(frappe.db.get_value("Stock Entry", doc.stock_entry, "company"), doc.company)

	def test_a_warehouse_of_another_company_is_refused_not_posted_elsewhere(self):
		other = frappe.db.get_value(
			"Company", {"name": ["not in", [self.company]], "is_group": 0}, "name"
		)
		if not other:
			self.skipTest("only one company on this site")
		got = create_milk_recording({
			"herd": self.herd,
			"recording_date": today(),
			"total_yield_kg": 12.0,
			"company": other,
			"remarks": MARKER,
		})
		self.assertFalse(got.get("ok"), "milk recorded under one company was posted into another's store")
		self.assertIn(self.warehouse, got.get("error") or "")

	def test_cancelling_takes_the_milk_back_out_of_stock(self):
		doc = self._record(company=self.company)
		self.assertTrue(doc.stock_entry, "no stock was posted")
		se, je = doc.stock_entry, doc.journal_entry
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Stock Entry", se, "docstatus"), 2)
		if je:
			self.assertEqual(frappe.db.get_value("Journal Entry", je, "docstatus"), 2)
