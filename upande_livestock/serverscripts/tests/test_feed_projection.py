# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""When each feed runs out, not how much of it there is.

"3,200 kg of silage" tells nobody anything — eleven days for this herd
structure, three weeks for last month's. The farm buys and cuts on a lead time,
so the only number worth a screen is a date.

The judgement these tests defend: A RAW MATERIAL LEAVES THE STORE TWO WAYS AND
BOTH ARE REAL. Hay goes out on the ration; wheat bran goes out as 280 kg of
every tonne of calves meal. Count only the first and the farm never runs out of
wheat bran. Count only the second and it never runs out of hay.
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.feeding import feed_projection as fp

HAY, SILAGE, WHEAT_BRAN, SORGHUM = "4040010034", "4040010082", "4040010020", "4040010091"


class TestTheDrawIsCountedBothWays(IntegrationTestCase):
	def setUp(self):
		self.rows = {r["item_code"]: r for r in fp.feed_projection({"days": 30})["items"]}

	def test_a_ration_ingredient_is_drawn_directly(self):
		row = self.rows.get(SILAGE)
		if not row:
			self.skipTest("no herd on this site is fed silage")
		self.assertGreater(row["direct_per_day"], 0)

	def test_a_concentrate_ingredient_is_drawn_through_the_concentrate(self):
		"""Wheat bran is in no TMR on this farm and leaves the store every day."""
		row = self.rows.get(WHEAT_BRAN)
		if not row:
			self.skipTest("wheat bran is not drawn on this site")
		self.assertEqual(row["direct_per_day"], 0)
		self.assertGreater(row["via_concentrate_per_day"], 0)
		self.assertTrue(row["concentrates"])

	def test_the_total_is_the_two_added(self):
		for row in self.rows.values():
			self.assertAlmostEqual(
				row["per_day"],
				row["direct_per_day"] + row["via_concentrate_per_day"],
				places=2, msg=row["item_code"],
			)

	def test_the_draw_is_in_the_units_the_store_holds(self):
		"""Hay is written in kilograms and stocked in bales. A projection in
		recipe units would say the farm has fourteen times the feed."""
		row = self.rows.get(HAY)
		if not row:
			self.skipTest("no herd on this site is fed hay")
		self.assertEqual(row["uom"], "BALE")
		per_head = [h["per_head"] for h in row["herds"]]
		self.assertTrue(all(q < 1 for q in per_head),
		                f"a bale a head a day would be absurd: {per_head}")


class TestWhenItRunsOut(IntegrationTestCase):
	def _one(self, on_hand, per_day):
		draw = {HAY: {"item_code": HAY, "direct_kg": per_day, "via_concentrate_kg": 0.0,
		              "herds": [], "concentrates": []}}
		with mock.patch.object(fp, "_draw_per_day", lambda: draw), \
		     mock.patch.object(fp, "_on_hand", lambda code: on_hand):
			return fp.feed_projection({"days": 30})["items"][0]

	def test_cover_is_stock_over_daily_draw(self):
		self.assertEqual(self._one(100.0, 10.0)["days_cover"], 10.0)

	def test_the_date_is_what_a_person_actually_reads(self):
		row = self._one(100.0, 10.0)
		self.assertEqual(row["runs_out_on"], add_days(today(), 10))

	def test_an_empty_store_runs_out_today(self):
		row = self._one(0.0, 10.0)
		self.assertEqual(row["days_cover"], 0.0)
		self.assertEqual(row["runs_out_on"], today())

	def test_a_feed_nothing_draws_has_no_date(self):
		"""Not "never" and not a crash — there is no such thing as running out."""
		row = self._one(500.0, 0.0)
		self.assertIsNone(row["days_cover"])
		self.assertIsNone(row["runs_out_on"])

	def test_a_decade_of_cover_is_not_reported_as_a_number(self):
		"""Cover measured in years is arithmetic on a rounding error."""
		self.assertIsNone(self._one(1_000_000.0, 0.01)["days_cover"])

	def test_the_series_a_chart_draws_falls_to_the_floor_and_stays(self):
		"""A store does not go negative; it stops."""
		row = self._one(50.0, 10.0)
		self.assertEqual(row["series"][0], 50.0)
		self.assertEqual(row["series"][5], 0.0)
		self.assertTrue(all(v >= 0 for v in row["series"]))
		self.assertEqual(len(row["series"]), 31)

	def test_what_runs_out_inside_the_horizon_is_called_out_separately(self):
		with mock.patch.object(fp, "_draw_per_day", lambda: {
			HAY: {"item_code": HAY, "direct_kg": 10.0, "via_concentrate_kg": 0.0,
			      "herds": [], "concentrates": []},
			SILAGE: {"item_code": SILAGE, "direct_kg": 1.0, "via_concentrate_kg": 0.0,
			         "herds": [], "concentrates": []},
		}), mock.patch.object(fp, "_on_hand", lambda code: 50.0 if code == HAY else 5000.0):
			got = fp.feed_projection({"days": 30})
		self.assertEqual([r["item_code"] for r in got["running_out"]], [HAY])

	def test_the_soonest_to_run_out_is_first(self):
		"""The list is a worklist, not an inventory."""
		got = fp.feed_projection({"days": 30})
		covers = [r["days_cover"] for r in got["items"] if r["days_cover"] is not None]
		self.assertEqual(covers, sorted(covers))


class TestWhatItPromisesAndWhatItDoesNot(IntegrationTestCase):
	def test_it_says_what_the_projection_rests_on(self):
		"""Head counts move. A projection that modelled that would be a forecast
		of a forecast; this one states its assumption so a person can check it."""
		got = fp.feed_projection({})
		self.assertIn("head counts", got["basis"])

	def test_the_dates_line_up_with_the_series(self):
		got = fp.feed_projection({"days": 14})
		self.assertEqual(len(got["dates"]), 15)
		self.assertEqual(got["dates"][0], today())
		for row in got["items"]:
			self.assertEqual(len(row["series"]), len(got["dates"]))

	def test_a_silly_horizon_is_clamped_rather_than_refused(self):
		"""A year out is already a guess; ten years is a guess about a guess."""
		self.assertEqual(fp.feed_projection({"days": 5000})["days"], 365)

	def test_no_horizon_and_a_zero_horizon_both_mean_the_default(self):
		"""Zero days of projection is not a thing anybody wants to see, so it
		reads as "unset" — the same as leaving it out."""
		self.assertEqual(fp.feed_projection({})["days"], fp.DEFAULT_HORIZON)
		self.assertEqual(fp.feed_projection({"days": 0})["days"], fp.DEFAULT_HORIZON)

	def test_it_writes_nothing(self):
		before = frappe.db.count("BOM")
		fp.feed_projection({"days": 30})
		self.assertEqual(frappe.db.count("BOM"), before)
