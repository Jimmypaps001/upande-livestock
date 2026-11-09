# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

# The Item link would otherwise pull in ERPNext's whole Item test-record set,
# whose warehouses need a custom_farm this site's Warehouse makes mandatory.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Item"]


class TestLivestockFeed(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("Livestock Feed", {"name": "_Test LF Item"})

	def tearDown(self):
		frappe.db.rollback()

	def _item(self):
		code = "_Test LF Item"
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{"doctype": "Item", "item_code": code, "item_name": "Test LF Meal",
				 "item_group": "All Item Groups", "stock_uom": "Kilogram"}
			).insert(ignore_permissions=True)
		return code

	def _feed(self, **kw):
		values = {"doctype": "Livestock Feed", "item": self._item(), "category": "Energy (grain / by-product)",
		          "dry_matter_pct": 88, "crude_protein_pct": 10, "carbohydrate_pct": 60}
		values.update(kw)
		return frappe.get_doc(values)

	def test_the_name_is_the_item_and_the_feed_name_comes_from_it(self):
		doc = self._feed().insert()
		self.assertEqual(doc.name, "_Test LF Item")
		self.assertEqual(doc.feed_name, "Test LF Meal")

	def test_a_percent_outside_0_100_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._feed(crude_protein_pct=120).insert()

	def test_the_dm_shares_may_not_exceed_a_hundred(self):
		with self.assertRaises(frappe.ValidationError):
			self._feed(crude_protein_pct=30, carbohydrate_pct=50, fibre_ndf_pct=30).insert()

	def test_a_raw_feed_needs_dry_matter_but_a_made_one_does_not(self):
		with self.assertRaises(frappe.ValidationError):
			self._feed(dry_matter_pct=0).insert()
		doc = self._feed(dry_matter_pct=0, category="Concentrate (made)").insert()
		self.assertTrue(doc.name)

	def test_one_record_per_item(self):
		self._feed().insert()
		with self.assertRaises(frappe.DuplicateEntryError):
			self._feed().insert()
