import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.feeding import _engine
from upande_livestock.serverscripts.feeding import feed_in_store as feed_in_store_mod
from upande_livestock.serverscripts.feeding.feed_in_store import feed_in_store

LACTATING_CONCENTRATE = "4040010086"
# Real, wrongly-flagged rows from the coordinator's report: a chemical stored
# in the feed store, and 35.5 tonnes of raw milk (livestock *output*, not
# feed) sitting in a warehouse this endpoint reads.
KNOWN_NON_FEED = ("1110009", "WestWood Dairy Milk (kg)")


def _a_herd_ration():
	"""(herd, tmr_item_code) for a live herd ration on this site."""
	herds = frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"])
	for h in herds:
		item = frappe.db.get_value("BOM", h.bom, "item")
		if item:
			return h.name, item
	return None, None


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

	def test_a_tmr_is_not_reported_as_a_concentrate(self):
		"""The bug this test pins: 'has a default BOM' used to be the whole
		concentrate test, and a TMR is manufactured too — so real rations like
		Bullying Heifers, Lactating Group 1/2 etc. were flagged as concentrates.
		Concentrate-ness is a line's role inside a herd's ration, not merely
		having a BOM; a TMR's own production item must come back "tmr", never
		"concentrate", even though Item.default_bom is set on it."""
		herd, tmr_item = _a_herd_ration()
		if not tmr_item:
			raise unittest.SkipTest("no herd on this site has a ration BOM")
		self.assertTrue(
			frappe.db.get_value("Item", tmr_item, "default_bom"),
			"fixture assumption failed: the TMR item should carry a default BOM",
		)
		res = feed_in_store()
		rows = [r for r in res["items"] if r["item_code"] == tmr_item]
		if not rows:
			raise unittest.SkipTest(f"{tmr_item} (herd {herd}'s ration) has no stock on this site")
		for r in rows:
			self.assertEqual(r["kind"], "tmr", r)
			self.assertFalse(r["is_concentrate"], r)

	def test_the_known_bought_in_concentrate_is_flagged(self):
		res = feed_in_store()
		rows = [r for r in res["items"] if r["item_code"] == LACTATING_CONCENTRATE]
		if not rows:
			raise unittest.SkipTest(f"{LACTATING_CONCENTRATE} has no stock on this site")
		for r in rows:
			self.assertEqual(r["kind"], "concentrate", r)
			self.assertTrue(r["is_concentrate"], r)

	def test_a_farm_mixed_meal_is_flagged_concentrate_not_ingredient(self):
		res = feed_in_store()
		mixed = [
			r
			for r in res["items"]
			if r["kind"] == "concentrate" and frappe.db.get_value("Item", r["item_code"], "default_bom")
		]
		if not mixed:
			raise unittest.SkipTest("no farm-mixed meal with a default BOM has stock on this site")
		for r in mixed:
			self.assertTrue(r["is_concentrate"], r)

	def test_bought_in_concentrates_without_a_bom_are_still_flagged(self):
		"""is_concentrate must not silently collapse to 'has a default BOM' —
		a bought-in concentrate named on Livestock Settings has none."""
		bought_in = _engine._bought_in_concentrates()
		res = feed_in_store()
		seen = False
		for r in res["items"]:
			if r["item_code"] in bought_in and not frappe.db.get_value("Item", r["item_code"], "default_bom"):
				seen = True
				self.assertEqual(r["kind"], "concentrate", r)
		if not seen:
			raise unittest.SkipTest("no bought-in, non-mixed concentrate has stock on this site")

	def test_a_raw_material_is_reported_as_an_ingredient(self):
		res = feed_in_store()
		tmr_items = {r["item_code"] for r in res["items"] if r["kind"] == "tmr"}
		concentrate_items = {r["item_code"] for r in res["items"] if r["kind"] == "concentrate"}
		plain = [
			r
			for r in res["items"]
			if r["item_code"] not in tmr_items and r["item_code"] not in concentrate_items
		]
		if not plain:
			raise unittest.SkipTest("no plain raw material has stock on this site")
		for r in plain:
			self.assertEqual(r["kind"], "ingredient", r)
			self.assertFalse(r["is_concentrate"], r)

	def test_every_row_is_a_genuine_feed_item(self):
		"""Everything reported must sit in the DAIRY item group — the group
		_engine's own docstring says every feed item, mixed or bought-in
		concentrate included, belongs to. A chemical or a dairy-processing
		output can still have a balance in a feed warehouse; that does not
		make it feed."""
		res = feed_in_store()
		self.assertTrue(res["items"])
		for r in res["items"]:
			self.assertEqual(frappe.db.get_value("Item", r["item_code"], "item_group"), "DAIRY", r)

	def test_known_non_feed_items_are_excluded(self):
		"""Regression for the coordinator's report: a CHEMICALS item and 35.5
		tonnes of raw milk (livestock output, not feed) both sit with a real
		balance in a feed warehouse on this site, and must not appear here."""
		res = feed_in_store()
		reported = {r["item_code"] for r in res["items"]}
		for code in KNOWN_NON_FEED:
			balance = frappe.db.exists("Bin", {"item_code": code, "actual_qty": [">", 0]})
			if not balance:
				raise unittest.SkipTest(f"{code} no longer has a positive balance anywhere on this site")
			self.assertNotIn(code, reported)

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


class TestTheFeedItemGroupIsTheFarmsToName(unittest.TestCase):
	"""The last hard-coded item group, and the same bug the drug picker had.

	`FEED_ITEM_GROUP = "DAIRY"` is what kaitet.local calls its feed catalogue
	(738 items). The live site has **no items at all** in `DAIRY`; its feed is
	in `Dairy Feed` (109) and `Dairy Others` (409). So this page shows an empty
	store on the site that matters, and looks like a farm with no feed rather
	than a page asking the wrong question.
	"""

	def test_the_group_comes_from_the_setting(self):
		with patch.object(frappe.db, "get_single_value", return_value="Dairy Feed"):
			self.assertEqual(feed_in_store_mod.feed_item_group(), "Dairy Feed")

	def test_an_unset_setting_keeps_the_old_constant(self):
		with patch.object(frappe.db, "get_single_value", return_value=None):
			self.assertEqual(feed_in_store_mod.feed_item_group(), "DAIRY")

	def test_the_setting_exists_and_points_at_item_group(self):
		f = frappe.get_meta("Livestock Settings").get_field("custom_feed_item_group")
		self.assertIsNotNone(f, "Livestock Settings has no custom_feed_item_group")
		self.assertEqual(f.fieldtype, "Link")
		self.assertEqual(f.options, "Item Group")

	def test_the_page_asks_for_the_configured_group(self):
		"""Not the constant — a page that reads the setting and then queries
		DAIRY anyway is the bug with an extra step."""
		seen = {}
		real = frappe.db.sql

		def spy(query, values=None, **kwargs):
			if values and "tabBin" in str(query):
				seen["group"] = values[-1]
				return []
			return real(query, values, **kwargs)

		with patch.object(feed_in_store_mod, "feed_item_group", return_value="Dairy Feed"), patch.object(
			frappe.db, "sql", side_effect=spy
		):
			feed_in_store()
		self.assertEqual(seen.get("group"), "Dairy Feed")
