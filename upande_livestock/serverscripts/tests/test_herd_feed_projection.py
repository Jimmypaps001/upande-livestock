# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The feed projection and paddock map endpoints, against the Mutara seed."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.projection.get_feed_projection import get_feed_projection
from upande_livestock.serverscripts.projection.get_paddock_map import get_paddock_map


class TestFeedProjectionEndpoint(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Herds", "Finishers"):
			self.skipTest("Mutara beef seed not present")

	def test_totals_are_the_sum_of_the_herds(self):
		r = get_feed_projection(12)
		self.assertEqual(r["weeks"], 12)
		self.assertEqual(r["total"]["head"], sum(h["head"] for h in r["herds"]))
		self.assertAlmostEqual(r["total"]["live_kg"], sum(h["live_kg"] for h in r["herds"]), delta=1.0)
		self.assertAlmostEqual(r["total"]["day_kg"], r["total"]["live_kg"] * r["settings"]["dm_intake_pct"] / 100, delta=1.0)

	def test_the_day_need_is_the_intake_share_of_live_weight(self):
		frappe.db.set_single_value("Livestock Settings", "dm_intake_pct", 3)
		try:
			r = get_feed_projection(4)
			self.assertEqual(r["settings"]["dm_intake_pct"], 3)
			self.assertAlmostEqual(r["total"]["day_kg"], r["total"]["live_kg"] * 0.03, delta=1.0)
		finally:
			frappe.db.rollback()

	def test_weeks_are_clamped_to_four_to_twenty_six(self):
		self.assertEqual(get_feed_projection(1)["weeks"], 4)
		self.assertEqual(get_feed_projection(99)["weeks"], 26)
		self.assertEqual(get_feed_projection("x")["weeks"], 12)
		self.assertEqual(len(get_feed_projection(26)["total"]["weeks"]["expected"]), 26)

	def test_scenarios_order_and_cumulative_grows(self):
		r = get_feed_projection(8)
		lo, hi = r["total"]["weeks"]["low"][-1], r["total"]["weeks"]["high"][-1]
		self.assertLessEqual(lo["avg_kg"], hi["avg_kg"])
		cum = [w["cumulative_kg"] for w in r["total"]["weeks"]["expected"]]
		self.assertEqual(cum, sorted(cum))

	def test_a_herd_filter_narrows_everything(self):
		r = get_feed_projection(8, "Finishers")
		self.assertEqual([h["herd"] for h in r["herds"]], ["Finishers"])
		self.assertEqual(r["total"]["head"], r["herds"][0]["head"])

	def test_calves_are_counted_but_not_fed(self):
		r = get_feed_projection(4)
		lg1 = next(h for h in r["herds"] if h["herd"] == "Lactation Group 1")
		self.assertEqual(lg1["head"], lg1["fed_heads"] + lg1["calves"])

	def test_feed_in_store_gives_days_left(self):
		r = get_feed_projection(12)
		self.assertGreater(r["stock"]["total_kg"], 0)
		today_rate = r["total"]["stock_kg"] / r["total"]["day_kg"]
		self.assertAlmostEqual(r["total"]["days_left"]["today_rate"], today_rate, delta=0.1)

	def test_feedlot_bands_cross(self):
		r = get_feed_projection(12)
		self.assertEqual(r["bands"]["names"], ["Starters", "Growers", "Finishers"])
		moved = [m for w in r["bands"]["weeks"] for m in w["moves"]]
		self.assertTrue(any(m["from"] == "Starters" and m["to"] == "Growers" for m in moved))

	def test_paddock_map_places_every_herd_and_judges_the_rotation(self):
		m = get_paddock_map()
		self.assertEqual(m["unplaced"], [])
		kinds = {p["kind"] for p in m["places"]}
		self.assertEqual(kinds, {"Paddock", "Pen"})
		rot = m["rotation"]
		self.assertEqual((rot["paddocks"], rot["grazing_herds"]), (7, 5))
		self.assertFalse(rot["enough"])
		self.assertEqual(sorted(m["resting"]), ["Paddock A2", "Paddock A5"])
		for p in m["places"]:
			if p["state"] == "occupied":
				self.assertEqual(p["heads"], sum(h["heads"] for h in p["herds"]))
			self.assertTrue(p["geojson"])
