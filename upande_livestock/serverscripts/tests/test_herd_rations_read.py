# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Reading every herd's ration, for the two editors that write it back.

The read half of `set_herd_ration`, and it carries one judgement worth
defending: LINES COME BACK IN THE UNITS THE RECIPE IS WRITTEN IN. Hay is 1.5 kg
on a lactating ration and stocked in BALE at 0.07. Handing an operator "0.105
BALE" where the recipe says "1.5 Kilogram" is not the same fact in another unit
— it is a fourteenth of the hay, in a number they cannot check against the
mixer.

It also reports whether each ration's stated output and its own ingredients add
up to the same number, because six of the live site's do not, and a ration that
issues less feed than it consumes is not something to leave for somebody to
notice.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding.herd_rations import herd_rations

HAY = "4040010034"


class TestReadingTheRations(IntegrationTestCase):
	def setUp(self):
		got = herd_rations({})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.got = got
		self.fed = [h for h in got["herds"] if h["bom"]]

	def test_every_herd_is_listed_whether_it_is_fed_or_not(self):
		"""A herd with no ration is the one somebody needs to find."""
		self.assertEqual(len(self.got["herds"]), frappe.db.count("Herds"))

	def test_a_fed_herd_carries_its_recipe_and_its_lines(self):
		self.assertTrue(self.fed, "no herd on this site has a ration")
		for h in self.fed:
			self.assertTrue(h["lines"], f"{h['herd']} has a BOM with no ingredients")
			self.assertTrue(h["ration_item"])

	def test_hay_comes_back_in_kilograms_not_bales(self):
		"""The units the mixer works to, not the units the store counts."""
		for h in self.fed:
			for line in h["lines"]:
				if line["item_code"] == HAY:
					self.assertEqual(line["uom"], "Kilogram")
					self.assertGreater(line["qty"], 0.5,
					                   "a fraction of a bale where kilograms were meant")
					return
		self.skipTest("no ration on this site carries hay")

	def test_the_day_is_the_ration_times_the_head_count(self):
		for h in self.fed:
			self.assertAlmostEqual(h["day_kg"], h["per_head_kg"] * h["heads"], places=3)

	def test_it_says_whether_the_output_and_the_ingredients_agree(self):
		for h in self.fed:
			total = sum(flt(line["qty"]) for line in h["lines"])
			self.assertAlmostEqual(h["lines_total"], total, places=3)
			self.assertEqual(h["balanced"], abs(total - h["per_head_kg"]) < 0.0005)

	def test_the_feeds_on_offer_are_ones_a_recipe_already_names(self):
		"""Not the whole item master — naming a new feed product is the farm's
		call, and a picker offering everything invites a ration of fence posts."""
		feeds = {f["value"] for f in self.got["feeds"]}
		self.assertTrue(feeds)
		self.assertLess(len(feeds), frappe.db.count("Item"))
		for h in self.fed:
			for line in h["lines"]:
				self.assertIn(line["item_code"], feeds,
				              f"{line['item_code']} is fed but not offered")

	def test_each_feed_says_what_is_in_store_and_in_what_unit(self):
		for f in self.got["feeds"]:
			self.assertIn("on_hand", f)
			self.assertTrue(f["uom"], f"{f['value']} has no stock unit")

	def test_it_writes_nothing(self):
		before = frappe.db.count("BOM")
		herd_rations({})
		self.assertEqual(frappe.db.count("BOM"), before)
