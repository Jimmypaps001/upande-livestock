# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A calf leaves its mother at the separation age; the alert says where it can go."""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.alerts import raise_alerts
from upande_livestock.serverscripts.common import calf_separation as cs
from upande_livestock.serverscripts.movement.eligibility import eligibility
from upande_livestock.serverscripts.tests.beef_fixtures import (
	clear_bands, isolate, make_animal, make_herd, move_animal, submit_weight,
)


def ago(days):
	return add_days(today(), -days)


class TestCalfSeparation(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		clear_bands()
		self.limit = frappe.db.get_single_value("Livestock Settings", "calf_separation_age_days")
		self.group = make_herd("ZZ CS Lactation", "Breeding").name
		self.starters = make_herd("ZZ CS Starters", "Fattening", 0, 250).name
		self.growers = make_herd("ZZ CS Growers", "Fattening", 250, 280).name
		self.heifers = make_herd("ZZ CS Weaner Heifers", "Other").name
		self.cow = make_animal(self.group, sex="Female", date_of_birth=ago(2800))
		patcher = mock.patch("upande_livestock.serverscripts.common.herd_movement.heifer_herds",
		                     return_value=[self.heifers])
		patcher.start()
		self.addCleanup(patcher.stop)

	def _calf(self, sex, age, weight=None):
		return make_animal(self.group, weight, sex=sex, date_of_birth=ago(age), dam=self.cow.name)

	def _alerts(self, *animals):
		return [a for a in raise_alerts.collect() if a["kind"] == "Calf Separation Due"
		        and a["animal"] in [x.name for x in animals]]

	def test_alert_at_exactly_the_separation_age(self):
		on_day = self._calf("Male", self.limit)
		day_before = self._calf("Male", self.limit - 1)
		self.assertEqual([a["animal"] for a in self._alerts(on_day, day_before)], [on_day.name])

	def test_female_calf_is_pointed_at_the_first_heifer_herd(self):
		heifer = self._calf("Female", self.limit + 5)
		(due,) = [c for c in cs.separation_due() if c["animal"] == heifer.name]
		self.assertEqual(due["options"], [{"stream": "Heifer", "herd": self.heifers}])
		self.assertEqual(due["over_days"], 5)

	def test_male_calf_is_offered_both_streams(self):
		bull = self._calf("Male", self.limit + 1, weight=262)
		(due,) = [c for c in cs.separation_due() if c["animal"] == bull.name]
		feedlot, breeding = due["options"]
		self.assertEqual((feedlot["stream"], feedlot["herd"]), ("Feedlot", self.growers))
		self.assertEqual(breeding["stream"], "Breeding")
		self.assertIn(self.group, breeding["herds"])

	def test_unweighed_bull_calf_goes_to_the_lowest_band(self):
		bull = self._calf("Male", self.limit + 1)
		(due,) = [c for c in cs.separation_due() if c["animal"] == bull.name]
		self.assertEqual(due["options"][0]["herd"], self.starters)

	def test_moving_the_calf_settles_the_alert(self):
		bull = self._calf("Male", self.limit + 3)
		raise_alerts.record(raise_alerts.collect())
		self.assertTrue(frappe.db.exists("Livestock Alert", {
			"alert_kind": "Calf Separation Due", "animal": bull.name, "status": "Open"}))
		move_animal(bull.name, self.starters)
		raise_alerts.refresh_calf_alert(bull.name)
		self.assertFalse(frappe.db.exists("Livestock Alert", {
			"alert_kind": "Calf Separation Due", "animal": bull.name, "status": "Open"}))

	def test_zero_switches_it_off(self):
		bull = self._calf("Male", self.limit + 30)
		frappe.db.set_single_value("Livestock Settings", "calf_separation_age_days", 0)
		self.assertEqual(self._alerts(bull), [])
		self.assertEqual(cs.separation_due(), [])

	def test_a_grown_animal_is_not_a_calf(self):
		old = make_animal(self.group, sex="Female", date_of_birth=ago(900), dam=self.cow.name)
		self.assertEqual([c for c in cs.separation_due() if c["animal"] == old.name], [])

	def test_eligibility_lists_it(self):
		bull = self._calf("Male", self.limit + 2)
		got = eligibility()
		self.assertIn(self.group, got["breeding_herds"])
		self.assertIn(bull.name, [c["animal"] for c in got["separation_due"]])
		self.assertIn(self.group, got["service_herds"])

	def test_head_breakdown_leaves_calves_unfed(self):
		self._calf("Male", 100)
		bull = make_animal(self.group, sex="Male", date_of_birth=ago(2000))
		got = cs.head_breakdown(self.group)
		self.assertEqual((got["animals"], got["calves"], got["fed"], got["bulls"], got["females"]),
		                 (3, 1, 2, 1, 1))
		self.assertTrue(bull)
