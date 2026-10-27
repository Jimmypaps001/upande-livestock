# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Average daily gain from a weighing history."""

from datetime import date

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common.gain import adg_between, herd_target_adg, weights_for
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, submit_weight


class TestGain(IntegrationTestCase):
	def setUp(self):
		isolate(self)

	def test_adg_two_points(self):
		pts = [(date(2026, 1, 1), 200.0), (date(2026, 1, 31), 230.0)]
		self.assertAlmostEqual(adg_between(pts), 1.0)

	def test_adg_single_point_is_none(self):
		self.assertIsNone(adg_between([(date(2026, 1, 1), 200.0)]))
		self.assertIsNone(adg_between([]))
		self.assertIsNone(adg_between([(date(2026, 1, 1), 200.0), (date(2026, 1, 1), 210.0)]))

	def test_birth_weight_is_first_point(self):
		herd = make_herd("ZZ Gain Calves", "Calf").name
		born = add_days(today(), -100)
		a = make_animal(herd, date_of_birth=born, birth_weight_kg=40)
		submit_weight(a.name, 140, days_ago=0)
		pts = weights_for(a.name)
		self.assertEqual(pts[0], (date.fromisoformat(str(born)), 40.0))
		self.assertEqual(len(pts), 2)
		self.assertAlmostEqual(adg_between(pts), 1.0)

	def test_window_filters_points(self):
		pts = [(date(2026, 1, 1), 200.0), (date(2026, 2, 1), 230.0), (date(2026, 3, 1), 290.0)]
		self.assertAlmostEqual(adg_between(pts, start=date(2026, 2, 1)), 60 / 28)
		self.assertIsNone(adg_between(pts, start=date(2026, 2, 2)))
		self.assertAlmostEqual(adg_between(pts, end=date(2026, 2, 1)), 30 / 31)

	def test_herd_target_prefers_herd_then_farm(self):
		with_target = make_herd("ZZ Gain T", "Fattening", target_adg_kg=0.9).name
		self.assertEqual(herd_target_adg(with_target), 0.9)
