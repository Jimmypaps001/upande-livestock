# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What to buy, and the one rule that decides it.

YOU DO NOT BUY WHAT YOU MIX. A concentrate with a recipe of its own is made on
this farm, so running short of it is answered by a Work Order, not a purchase —
and ordering a tonne of the farm's own "Calves Meal" formulation from a
supplier who has never heard of it is the mistake this exists to stop. What a
short mixed concentrate really means is that its RAW MATERIALS need buying, and
the projection already counts those.

The second judgement: HOW MUCH is expressed as a target in DAYS, not in
kilograms. "Enough to reach the end of the month" survives a herd change; a
target in kilograms is wrong the morning after somebody splits a group.
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding import feed_procurement as proc
from upande_livestock.serverscripts.feeding.create_feed_request import create_feed_request

MINERAL, LIMESTONE = "4040010052", "4040010029"


def _draw(**per_day):
	return {
		code: {"item_code": code, "direct_kg": qty, "via_concentrate_kg": 0.0,
		       "herds": [], "concentrates": []}
		for code, qty in per_day.items()
	}


class TestWhatTheFarmBuysAndWhatItMixes(IntegrationTestCase):
	def test_a_mixed_concentrate_is_never_ordered(self):
		"""Its recipe is the farm's own; no supplier stocks it."""
		rows = proc.feed_procurement({"target_days": 60})["items"]
		codes = {r["item_code"] for r in rows}
		for mixed in ("Calves Meal", "Weaner Meal", "Bullying Heifer Meal", "Dry Cows  Meal"):
			self.assertNotIn(mixed, codes, f"{mixed} is mixed here, not bought")

	def test_the_raw_materials_it_is_mixed_from_are(self):
		"""Which is how a short concentrate actually gets fixed."""
		rows = {r["item_code"] for r in proc.feed_procurement({"target_days": 365})["items"]}
		self.assertTrue(rows, "nothing to buy even at a year of cover")
		self.assertTrue(
			rows & {"4040010020", "4040020044", "4040010026"},
			"no concentrate raw material appears in the order",
		)

	def test_a_bought_in_concentrate_would_be_ordered(self):
		"""The exception the settings list exists to express."""
		with mock.patch.object(proc.feeding, "_bought_in_concentrates",
		                       lambda: {"Calves Meal"}):
			mixed, bought = proc._mixed_on_this_farm()
		self.assertIn("Calves Meal", bought)
		self.assertNotIn("Calves Meal", mixed)

	def test_everything_offered_says_which_it_is(self):
		for row in proc.feed_procurement({"target_days": 60})["items"]:
			self.assertIn(row["source"], ("Raw material", "Bought in"))


class TestHowMuchToBuy(IntegrationTestCase):
	def _rows(self, target_days, on_hand, per_day=10.0):
		with mock.patch.object(proc, "_draw_per_day", lambda: _draw(**{MINERAL: per_day})), \
		     mock.patch.object(proc, "_on_hand", lambda code: on_hand), \
		     mock.patch.object(proc, "_mixed_on_this_farm", lambda: (set(), set())):
			return proc.feed_procurement({"target_days": target_days})["items"]

	def test_it_orders_the_gap_to_the_target(self):
		row = self._rows(30, on_hand=100.0)[0]
		self.assertEqual(row["order_qty"], 200.0)   # 30 days x 10 - 100 on hand

	def test_a_feed_that_already_lasts_is_not_ordered(self):
		self.assertEqual(self._rows(30, on_hand=500.0), [])

	def test_it_rounds_up_rather_than_down(self):
		"""Rounding down reintroduces the shortfall the arithmetic removes.
		Nobody buys a third of a kilogram of limestone."""
		row = self._rows(30, on_hand=99.5)[0]
		self.assertEqual(row["order_qty"], 201.0)

	def test_an_empty_store_orders_the_whole_target(self):
		row = self._rows(30, on_hand=0.0)[0]
		self.assertEqual(row["order_qty"], 300.0)
		self.assertEqual(row["days_cover"], 0.0)

	def test_the_soonest_to_run_out_is_first(self):
		"""The list is a worklist, not an inventory."""
		rows = proc.feed_procurement({"target_days": 60})["items"]
		covers = [r["days_cover"] for r in rows if r["days_cover"] is not None]
		self.assertEqual(covers, sorted(covers))

	def test_a_silly_target_is_clamped(self):
		self.assertEqual(proc.feed_procurement({"target_days": 5000})["target_days"], 365)


class TestRaisingTheOrder(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _raise(self, items, **kw):
		return create_feed_request({"items": items, "target_days": 28, **kw})

	def test_one_request_carries_every_line(self):
		"""Six requests for one supplier trip is six things to chase."""
		got = self._raise([{"item_code": MINERAL, "qty": 500},
		                   {"item_code": LIMESTONE, "qty": 200}])
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["lines"], 2)
		doc = frappe.get_doc("Material Request", got["name"])
		self.assertEqual(len(doc.items), 2)

	def test_it_is_left_in_draft(self):
		"""Committing the farm to a purchase belongs to whoever talks to the
		supplier, not to the screen that did the arithmetic."""
		got = self._raise([{"item_code": MINERAL, "qty": 500}])
		self.assertEqual(frappe.db.get_value("Material Request", got["name"], "docstatus"), 0)

	def test_it_is_a_purchase_not_a_transfer(self):
		got = self._raise([{"item_code": MINERAL, "qty": 500}])
		self.assertEqual(
			frappe.db.get_value("Material Request", got["name"], "material_request_type"),
			"Purchase")

	def test_it_is_wanted_later_than_it_was_ordered(self):
		"""A schedule date of today reads as "needed before it was asked for"."""
		got = self._raise([{"item_code": MINERAL, "qty": 500}])
		doc = frappe.get_doc("Material Request", got["name"])
		self.assertGreater(str(doc.schedule_date), str(doc.transaction_date))

	def test_the_same_feed_twice_is_one_line_for_the_total(self):
		"""Two lines for one item is a supplier's invoice nobody can reconcile."""
		got = self._raise([{"item_code": MINERAL, "qty": 300},
		                   {"item_code": MINERAL, "qty": 200}])
		self.assertEqual(got["lines"], 1)
		self.assertEqual(flt(got["items"][0]["qty"]), 500.0)

	def test_an_empty_order_is_refused(self):
		got = self._raise([])
		self.assertIn("Nothing to order", got.get("error", ""))

	def test_a_zero_quantity_is_not_a_line(self):
		got = self._raise([{"item_code": MINERAL, "qty": 0}])
		self.assertIn("Nothing to order", got.get("error", ""))

	def test_an_item_that_is_not_on_the_site_is_refused(self):
		got = self._raise([{"item_code": "NO-SUCH-FEED", "qty": 10}])
		self.assertIn("not an item", got.get("error", ""))

	def test_it_is_delivered_into_the_feed_store(self):
		got = self._raise([{"item_code": MINERAL, "qty": 500}])
		doc = frappe.get_doc("Material Request", got["name"])
		self.assertEqual(doc.items[0].warehouse, got["warehouse"])
		self.assertTrue(got["farm"], "the request carries no farm")
