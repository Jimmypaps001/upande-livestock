# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the herd movement rules promise.

Days come from settings, not from a herd's name — a farm that renames "2-4"
must not change how long its calves stay there. Getting that wrong is invisible
until an animal is in the wrong place.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from upande_livestock.serverscripts.common import herd_movement as hm


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

	def test_heifer_herds_are_read_from_the_settings_table_and_exposed(self):
		from unittest import mock

		from upande_livestock.serverscripts.movement import eligibility as elig
		from upande_livestock.serverscripts.mobile import get_bootstrap_bundle as boot

		fake = frappe._dict(heifer_herds=[
			frappe._dict(herd="H-A"), frappe._dict(herd="H-B"), frappe._dict(herd="H-A"), frappe._dict(herd=None),
		])
		with mock.patch.object(hm, "settings", return_value=fake):
			self.assertEqual(hm.heifer_herds(), ["H-A", "H-B"])
		with mock.patch.object(hm, "settings", return_value=frappe._dict()):
			self.assertEqual(hm.heifer_herds(), [], "unconfigured means empty, so clients fall back")
		with mock.patch.object(hm, "heifer_herds", return_value=["H-A"]):
			self.assertEqual(elig.eligibility()["heifer_herds"], ["H-A"])
			herds = boot.get_bootstrap_bundle().get("herds", [])
			self.assertTrue(all("is_heifer" in h for h in herds))
			self.assertTrue(all(h["is_heifer"] == (h["name"] == "H-A") for h in herds))

	def test_in_calf_and_calf_herds_are_read_from_settings_and_exposed(self):
		from unittest import mock

		from upande_livestock.serverscripts.movement import eligibility as elig
		from upande_livestock.serverscripts.mobile import get_bootstrap_bundle as boot

		fake = frappe._dict(
			in_calf_herds=[frappe._dict(herd="IC-A"), frappe._dict(herd="IC-A"), frappe._dict(herd=None)],
			calf_herds=[frappe._dict(herd="C-A"), frappe._dict(herd="C-B")],
		)
		with mock.patch.object(hm, "settings", return_value=fake):
			self.assertEqual(hm.in_calf_herds(), ["IC-A"])
			self.assertEqual(hm.calf_group_herds(), ["C-A", "C-B"])
		with mock.patch.object(hm, "settings", return_value=frappe._dict()):
			self.assertEqual(hm.in_calf_herds(), [])
			self.assertEqual(hm.calf_group_herds(), [])
		with mock.patch.object(hm, "in_calf_herds", return_value=["IC-A"]), mock.patch.object(
			hm, "calf_group_herds", return_value=["C-A"]
		):
			out = elig.eligibility()
			self.assertEqual(out["in_calf_herds"], ["IC-A"])
			self.assertEqual(out["calf_group_herds"], ["C-A"])
			herds = boot.get_bootstrap_bundle().get("herds", [])
			self.assertTrue(all(h["is_in_calf"] == (h["name"] == "IC-A") for h in herds))
			self.assertTrue(all(h["is_calf"] == (h["name"] == "C-A") for h in herds))

	def test_service_offers_the_top_rung_only(self):
		herds = hm.service_herds()
		rungs = hm.growth_ladder()
		if not (herds and rungs):
			raise unittest.SkipTest("not configured")
		self.assertIn(rungs[-1]["herd"], herds)
		for rung in rungs[:-1]:
			self.assertNotIn(rung["herd"], herds, "a young calf is never offered for service")

	def test_a_calf_is_not_servable(self):
		rungs = hm.growth_ladder()
		if not rungs:
			raise unittest.SkipTest("no ladder")
		animal = frappe.db.get_value("Animal", {"current_herd": rungs[0]["herd"]}, "name")
		if not animal:
			raise unittest.SkipTest("no animal in the first herd")
		self.assertFalse(hm.is_servable(animal))

	def test_a_cow_is_not_servable_before_the_post_calving_wait(self):
		wait = hm.service_wait_days()
		if not wait:
			raise unittest.SkipTest("no post-calving wait configured")
		herds = hm.service_herds()
		animal = frappe.db.get_value(
			"Animal", {"current_herd": ["in", herds]}, "name"
		) if herds else None
		if not animal:
			raise unittest.SkipTest("no animal in a servable herd")
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
		for cattle, not the 270 that "nine months" rounds to."""
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


class TestAnUnsetTimingIsItsDefaultNotOff(unittest.TestCase):
	"""herd_movement read its timings as `int(s.get(key) or 0)`, so a setting
	never filled in switched its rule off (min service age 0, no open-days
	limit) instead of taking the documented default, and gestation fell back to
	270 days where the defaults say 280."""

	def test_unset_settings_read_as_their_defaults(self):
		from unittest.mock import patch

		from upande_livestock.serverscripts.common import herd_movement as HM
		from upande_livestock.serverscripts.common import timings

		with patch.object(timings, "read_setting", return_value=None):
			self.assertEqual(HM.service_wait_days(), timings.TIMING_DEFAULTS["post_calving_optimal_service_days"])
			self.assertEqual(HM.get_timing("min_service_age_months"), 15)
			self.assertEqual(HM.get_timing("gestation_period_days"), 280)


class TestCowHerd(unittest.TestCase):
	"""The herd a cow goes to when she calves, and is served again from."""

	def _settings(self, cow):
		from unittest import mock

		return mock.patch.object(hm, "settings", return_value=frappe._dict(cow_herd=cow))

	def test_it_is_read_from_settings_when_it_names_a_herd(self):
		from unittest import mock

		with self._settings("COWS"), mock.patch.object(frappe.db, "exists", return_value=True):
			self.assertEqual(hm.cow_herd(), "COWS")
		with self._settings("GONE"), mock.patch.object(frappe.db, "exists", return_value=False):
			self.assertIsNone(hm.cow_herd())
		with self._settings(None):
			self.assertIsNone(hm.cow_herd())

	def test_it_is_a_servable_herd_beside_the_ladder_rungs(self):
		from unittest import mock

		ladder = [{"herd": "TOP", "exits_on_service": 1}, {"herd": "LOW", "exits_on_service": 0}]
		with mock.patch.object(hm, "growth_ladder", return_value=ladder), mock.patch.object(
			hm, "cow_herd", return_value="COWS"
		):
			self.assertEqual(hm.service_herds(), ["TOP", "COWS"])
		with mock.patch.object(hm, "growth_ladder", return_value=ladder), mock.patch.object(
			hm, "cow_herd", return_value=None
		):
			self.assertEqual(hm.service_herds(), ["TOP"])

	def test_a_cow_in_the_cow_herd_past_the_wait_is_servable(self):
		from unittest import mock

		row = frappe._dict(current_herd="COWS", last_calving_date=add_days(today(), -400), repro_status="Open")
		with mock.patch.object(hm, "service_herds", return_value=["COWS"]), mock.patch.object(
			frappe.db, "get_value", return_value=row
		), mock.patch.object(hm, "service_wait_days", return_value=60), mock.patch.object(
			hm, "open_days", return_value=400
		), mock.patch.object(hm, "has_open_service", return_value=False):
			self.assertTrue(hm.is_servable("A1"))
