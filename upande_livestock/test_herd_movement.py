# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the herd movement rules promise.

The two that matter most, because getting either wrong is invisible until an
animal is in the wrong place:

  * days come from settings, not from a herd's name — a farm that renames "2-4"
    must not change how long its calves stay there;
  * Steamers' duration belongs to the ROUTE. A first-time heifer arrives with
    three months to calving and a cow from the low-yield herd with two, so
    asking the herd alone would give one answer where two are needed.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from upande_livestock import herd_movement as hm


class TestGrowthLadder(IntegrationTestCase):
	def setUp(self):
		if not hm.growth_ladder():
			raise unittest.SkipTest("no growth ladder configured on this site")

	def test_the_ladder_is_ordered(self):
		"""Row order is the movement order, so it must come back in idx order."""
		rungs = hm.growth_ladder()
		self.assertEqual([r["idx"] for r in rungs], sorted(r["idx"] for r in rungs))

	def test_each_rung_knows_the_one_after_it(self):
		rungs = hm.growth_ladder()
		for i, rung in enumerate(rungs[:-1]):
			self.assertEqual(hm.next_growth_herd(rung["herd"]), rungs[i + 1]["herd"])
		self.assertIsNone(hm.next_growth_herd(rungs[-1]["herd"]), "the top rung leads nowhere")

	def test_a_herd_off_the_ladder_has_no_position(self):
		self.assertIsNone(hm.ladder_position("__not_a_herd__"))
		self.assertIsNone(hm.next_growth_herd("__not_a_herd__"))

	def test_days_are_read_from_settings_not_from_the_name(self):
		"""'2-4' is a label. If the days were derived from it, renaming the herd
		would silently change how long a calf stays."""
		for rung in hm.growth_ladder():
			if rung["exits_on_service"]:
				continue
			self.assertIsInstance(rung["days_in_herd"], int)
			# nothing in the resolver may parse the herd name
			self.assertNotIn(rung["herd"], str(rung["days_in_herd"]))

	def test_the_last_rung_is_left_by_being_served(self):
		rungs = hm.growth_ladder()
		self.assertTrue(rungs[-1]["exits_on_service"],
		                "the ladder must end at a rung an animal leaves by being served")

	def test_a_service_rung_is_never_due_on_time(self):
		"""She leaves when she is served, so a day count must not push her on."""
		rung = [r for r in hm.growth_ladder() if r["exits_on_service"]]
		if not rung:
			raise unittest.SkipTest("no service rung configured")
		animal = frappe.db.get_value("Animal", {"current_herd": rung[0]["herd"]}, "name")
		if not animal:
			raise unittest.SkipTest("no animal in the service rung")
		self.assertIsNone(hm.growth_move_due(animal))


class TestSteamersRoute(IntegrationTestCase):
	"""The dry herd takes two streams with different dry periods."""

	def test_a_heifer_gets_the_longer_dry_period(self):
		s = hm.settings()
		if not s.get("incalf_heifer_herd"):
			raise unittest.SkipTest("no incalf heifer herd configured")
		self.assertEqual(hm.steamer_days_for(s.get("incalf_heifer_herd")),
		                 int(s.get("steamer_days_from_heifers")))

	def test_a_cow_from_the_low_yield_herd_gets_the_shorter_one(self):
		s = hm.settings()
		self.assertEqual(hm.steamer_days_for(s.get("low_yield_herd")),
		                 int(s.get("steamer_days_from_lactation")))

	def test_the_two_routes_differ(self):
		"""If they were the same the distinction would be decoration."""
		s = hm.settings()
		if not (s.get("steamer_days_from_heifers") and s.get("steamer_days_from_lactation")):
			raise unittest.SkipTest("steamer durations not configured")
		self.assertNotEqual(int(s.get("steamer_days_from_heifers")),
		                    int(s.get("steamer_days_from_lactation")))

	def test_an_unknown_origin_falls_back_to_the_lactation_route(self):
		s = hm.settings()
		self.assertEqual(hm.steamer_days_for(None), int(s.get("steamer_days_from_lactation")))


class TestCalfIntake(IntegrationTestCase):
	def test_sex_decides_the_herd(self):
		s = hm.settings()
		if not (s.get("female_calf_herd") and s.get("male_calf_herd")):
			raise unittest.SkipTest("calf herds not configured")
		self.assertEqual(hm.calf_herd("Female"), s.get("female_calf_herd"))
		self.assertEqual(hm.calf_herd("Male"), s.get("male_calf_herd"))

	def test_the_female_herd_is_the_first_rung(self):
		"""Otherwise a calf lands somewhere the ladder cannot carry her on from."""
		s = hm.settings()
		rungs = hm.growth_ladder()
		if not (rungs and s.get("female_calf_herd")):
			raise unittest.SkipTest("not configured")
		self.assertEqual(s.get("female_calf_herd"), rungs[0]["herd"])

	def test_an_unstated_sex_is_treated_as_female(self):
		"""Safer: she joins the ladder rather than a selling window."""
		s = hm.settings()
		self.assertEqual(hm.calf_herd(None), s.get("female_calf_herd"))
		self.assertEqual(hm.calf_herd(""), s.get("female_calf_herd"))


class TestBullCullWindow(IntegrationTestCase):
	def test_no_window_when_the_farm_does_not_sell_bulls(self):
		s = hm.settings()
		if s.get("cull_bulls_after_birth"):
			raise unittest.SkipTest("this site does sell bull calves off")
		animal = frappe.db.get_value("Animal", {"sex": "Male"}, "name")
		if animal:
			self.assertIsNone(hm.bull_cull_status(animal))

	def test_the_warning_point_is_a_share_of_the_window(self):
		s = hm.settings()
		if not s.get("cull_bulls_after_birth"):
			raise unittest.SkipTest("bull culling is off on this site")
		window = int(s.get("bull_cull_max_days"))
		pct = float(s.get("bull_cull_warn_percent") or 75)
		animal = frappe.db.get_value(
			"Animal", {"sex": "Male", "current_herd": s.get("male_calf_herd")}, "name"
		)
		if not animal:
			raise unittest.SkipTest("no bull calf in the male calf herd")
		st = hm.bull_cull_status(animal)
		self.assertAlmostEqual(st["warn_after_days"], window * pct / 100.0, places=4)
		self.assertEqual(st["window_days"], window)
		self.assertEqual(st["warn"], st["days_on_farm"] >= st["warn_after_days"])

	def test_a_female_is_never_in_a_cull_window(self):
		animal = frappe.db.get_value("Animal", {"sex": "Female"}, "name")
		if not animal:
			raise unittest.SkipTest("no female animal on this site")
		self.assertIsNone(hm.bull_cull_status(animal))


class TestEligibility(IntegrationTestCase):
	"""Derived from where an animal stands — never marked by hand."""

	def test_milking_offers_only_the_lactation_groups(self):
		s = hm.settings()
		herds = hm.milking_herds()
		if not herds:
			raise unittest.SkipTest("lactation herds not configured")
		self.assertIn(s.get("high_yield_herd"), herds)
		self.assertIn(s.get("low_yield_herd"), herds)
		for rung in hm.growth_ladder():
			self.assertNotIn(rung["herd"], herds, "a growth herd is never in milk")

	def test_service_offers_the_top_rung_and_cows_in_milk(self):
		herds = hm.service_herds()
		rungs = hm.growth_ladder()
		if not (herds and rungs):
			raise unittest.SkipTest("not configured")
		self.assertIn(rungs[-1]["herd"], herds)
		for rung in rungs[:-1]:
			self.assertNotIn(rung["herd"], herds, "a young calf is never offered for service")

	def test_a_calf_is_neither_milkable_nor_servable(self):
		rungs = hm.growth_ladder()
		if not rungs:
			raise unittest.SkipTest("no ladder")
		animal = frappe.db.get_value("Animal", {"current_herd": rungs[0]["herd"]}, "name")
		if not animal:
			raise unittest.SkipTest("no animal in the first herd")
		self.assertFalse(hm.is_milkable(animal))
		self.assertFalse(hm.is_servable(animal))

	def test_a_cow_is_not_servable_before_the_post_calving_wait(self):
		wait = hm.service_wait_days()
		if not wait:
			raise unittest.SkipTest("no post-calving wait configured")
		herds = hm.milking_herds()
		animal = frappe.db.get_value(
			"Animal", {"current_herd": ["in", herds]}, "name"
		) if herds else None
		if not animal:
			raise unittest.SkipTest("no animal in a lactation herd")
		original = frappe.db.get_value("Animal", animal, "last_calving_date")
		try:
			frappe.db.set_value("Animal", animal, "last_calving_date",
			                    add_days(today(), -(wait - 1)), update_modified=False)
			frappe.clear_document_cache("Animal", animal)
			self.assertFalse(hm.is_servable(animal), "too soon after calving")
			frappe.db.set_value("Animal", animal, "last_calving_date",
			                    add_days(today(), -(wait + 1)), update_modified=False)
			frappe.clear_document_cache("Animal", animal)
			self.assertTrue(hm.is_servable(animal), "past the wait")
		finally:
			frappe.db.set_value("Animal", animal, "last_calving_date", original, update_modified=False)
			frappe.clear_document_cache("Animal", animal)


class TestGestation(IntegrationTestCase):
	def test_calving_is_gestation_after_conception(self):
		"""Gestation comes from settings — this site runs 280 days, the standard
		for dairy cattle, not the 270 that "nine months" rounds to."""
		days = int(hm.settings().get("gestation_period_days") or 0) or 270
		self.assertEqual(
			hm.expected_calving_date("2026-01-01"), getdate(add_days("2026-01-01", days))
		)

	def test_gestation_is_held_in_exactly_one_place(self):
		"""Two fields holding the same number drift. The Herd Movement tab reads
		the General tab's Gestation Period rather than keeping its own copy."""
		meta = frappe.get_meta("Livestock Settings")
		names = [f.fieldname for f in meta.fields if "gestation" in f.fieldname]
		self.assertEqual(names.count("gestation_period_days"), 1)
		self.assertNotIn("gestation_days_advice", names)

	def test_no_conception_no_date(self):
		self.assertIsNone(hm.expected_calving_date(None))
