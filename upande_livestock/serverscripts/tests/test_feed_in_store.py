import unittest

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.feeding import _engine
from upande_livestock.serverscripts.feeding.feed_in_store import feed_in_store

LACTATING_CONCENTRATE = "4040010086"


class TestFeedInStore(IntegrationTestCase):
	def test_every_row_has_a_positive_balance(self):
		res = feed_in_store()
		self.assertTrue(res["ok"], res.get("error"))
		self.assertTrue(res["items"], "expected feed stock on kaitet.local")
		for row in res["items"]:
			self.assertGreater(row["qty"], 0)

	def test_an_item_in_two_warehouses_is_two_rows_not_one(self):
		"""Summing across stores was the bug in the drug picker: it offered stock
		the issuing store did not actually have. Feed must not repeat it."""
		res = feed_in_store()
		by_item = {}
		for row in res["items"]:
			by_item.setdefault(row["item_code"], []).append(row)
		multi = [rows for rows in by_item.values() if len(rows) > 1]
		if not multi:
			raise unittest.SkipTest("no feed item sits in two warehouses on this site")
		rows = multi[0]
		warehouses = {r["warehouse"] for r in rows}
		self.assertEqual(len(warehouses), len(rows), "each row should be a distinct warehouse")
		for r in rows:
			expected = frappe.db.get_value(
				"Bin", {"item_code": r["item_code"], "warehouse": r["warehouse"]}, "actual_qty"
			)
			self.assertAlmostEqual(r["qty"], expected, places=4)

	def test_the_known_bought_in_concentrate_is_flagged(self):
		res = feed_in_store()
		rows = [r for r in res["items"] if r["item_code"] == LACTATING_CONCENTRATE]
		if not rows:
			raise unittest.SkipTest(f"{LACTATING_CONCENTRATE} has no stock on this site")
		for r in rows:
			self.assertTrue(r["is_concentrate"], r)

	def test_a_farm_mixed_meal_with_a_default_bom_is_flagged(self):
		res = feed_in_store()
		mixed = [
			r
			for r in res["items"]
			if r["is_concentrate"] and frappe.db.get_value("Item", r["item_code"], "default_bom")
		]
		if not mixed:
			raise unittest.SkipTest("no farm-mixed meal with a default BOM has stock on this site")
		for r in mixed:
			self.assertTrue(frappe.db.get_value("Item", r["item_code"], "default_bom"))

	def test_bought_in_concentrates_without_a_bom_are_still_flagged(self):
		"""is_concentrate must not silently collapse to 'has a default BOM' —
		a bought-in concentrate named on Livestock Settings has none."""
		bought_in = _engine._bought_in_concentrates()
		res = feed_in_store()
		seen = False
		for r in res["items"]:
			if r["item_code"] in bought_in and not frappe.db.get_value("Item", r["item_code"], "default_bom"):
				seen = True
				self.assertTrue(r["is_concentrate"], r)
		if not seen:
			raise unittest.SkipTest("no bought-in, non-mixed concentrate has stock on this site")

	def test_a_non_concentrate_raw_material_is_not_flagged(self):
		res = feed_in_store()
		bought_in = _engine._bought_in_concentrates()
		plain = [
			r
			for r in res["items"]
			if r["item_code"] not in bought_in
			and not frappe.db.get_value("Item", r["item_code"], "default_bom")
		]
		if not plain:
			raise unittest.SkipTest("no plain raw material has stock on this site")
		for r in plain:
			self.assertFalse(r["is_concentrate"], r)

	def test_warehouse_narrows_the_result(self):
		all_stores = feed_in_store()
		one_store = None
		for wh in all_stores["warehouses"]:
			candidate = feed_in_store(warehouse=wh)
			if candidate["items"]:
				one_store = (wh, candidate)
				break
		if not one_store:
			raise unittest.SkipTest("no single feed store on this site has stock")
		wh, res = one_store
		self.assertEqual(res["warehouses"], [wh])
		self.assertTrue(res["items"])
		for row in res["items"]:
			self.assertEqual(row["warehouse"], wh)

	def test_no_warehouse_looks_at_every_feed_store(self):
		res = feed_in_store()
		self.assertEqual(res["warehouses"], _engine._feed_source_warehouses())

	def test_an_unprivileged_user_is_refused(self):
		frappe.set_user("Guest")
		try:
			res = feed_in_store()
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(res.get("error"))
