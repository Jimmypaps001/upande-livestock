# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Mutara's stores, settings and opening stock (demo/seed_mutara_stores)."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.demo import seed_mutara_stores as seed


class TestMutaraStores(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Warehouse", seed.full("Hay Store")):
			self.skipTest("Mutara stores not seeded")

	def test_every_store_exists_under_mutara(self):
		for name in seed.STORES:
			self.assertEqual(frappe.db.get_value("Warehouse", seed.full(name), "parent_warehouse"), seed.PARENT)

	def test_the_old_drug_store_name_is_gone(self):
		self.assertFalse(frappe.db.exists("Warehouse", seed.full("Livestock Drug Store")))

	def test_settings_point_at_the_stores(self):
		self.assertEqual(frappe.db.get_single_value("Livestock Settings", "custom_feed_wip_warehouse"), seed.full("Mixing Store"))
		sources = frappe.get_all("Livestock Feed Warehouse", filters={"parent": "Livestock Settings"}, pluck="warehouse")
		for name in seed.FEED_SOURCES:
			self.assertIn(seed.full(name), sources)

	def test_opening_stock_is_in_the_right_stores(self):
		for item, store, qty, _rate in seed.OPENING:
			self.assertGreaterEqual(
				frappe.db.get_value("Bin", {"item_code": item, "warehouse": seed.full(store)}, "actual_qty") or 0, 0.01)

	def test_every_herd_has_a_paddock_or_pen_of_the_right_type(self):
		for herd, place in seed.PLACEMENT.items():
			wh = frappe.db.get_value("Herds", herd, "paddock")
			self.assertEqual(wh, seed.full(place))
			want = "Pen" if herd in ("Starters", "Growers", "Finishers") else "Paddock"
			self.assertEqual(frappe.db.get_value("Warehouse", wh, "warehouse_type"), want)

	def test_rerunning_the_seed_changes_nothing(self):
		bins = frappe.db.sql("select count(*), sum(actual_qty) from tabBin")
		warehouses = frappe.db.count("Warehouse")
		seed.run()
		self.assertEqual(frappe.db.sql("select count(*), sum(actual_qty) from tabBin"), bins)
		self.assertEqual(frappe.db.count("Warehouse"), warehouses)
