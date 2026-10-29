# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Sire inference from herd history."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.serverscripts.common import sire_inference as si
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, move_animal


def ago(days):
	return add_days(today(), -days)


class TestSireInference(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.group = make_herd("ZZ SI Group", "Breeding").name
		self.other = make_herd("ZZ SI Other", "Breeding").name
		self.cow = make_animal(self.group, sex="Female", date_of_birth=ago(2500))
		self.conceived = ago(100)

	def _bull(self, herd=None, born=1500):
		return make_animal(herd or self.group, sex="Male", date_of_birth=ago(born))

	def test_one_bull_is_inferred_with_a_basis(self):
		bull = self._bull()
		got = si.infer_sire(self.cow.name, self.conceived)
		self.assertEqual((got["sire"], got["inferred"]), (bull.name, True))
		self.assertIn("was in ZZ SI Group from", got["basis"])
		self.assertEqual(len(got["candidates"]), 1)

	def test_two_overlapping_bulls_give_candidates_and_no_sire(self):
		a, b = self._bull(), self._bull()
		got = si.infer_sire(self.cow.name, self.conceived)
		self.assertIsNone(got["sire"])
		self.assertFalse(got["inferred"])
		self.assertEqual(sorted(c["animal"] for c in got["candidates"]), sorted([a.name, b.name]))

	def test_no_bull_is_blank_with_a_reason(self):
		got = si.infer_sire(self.cow.name, self.conceived)
		self.assertEqual((got["sire"], got["candidates"]), (None, []))
		self.assertIn("No bull", got["basis"])

	def test_bull_under_breeding_age_is_ignored(self):
		min_months = frappe.db.get_single_value("Livestock Settings", "breeding_bull_min_age_months")
		young = make_animal(self.group, sex="Male", date_of_birth=add_months(self.conceived, -(int(min_months) - 1)))
		self.assertEqual(si.candidate_sires(self.cow.name, self.conceived), [])
		old_enough = make_animal(self.group, sex="Male", date_of_birth=add_months(self.conceived, -int(min_months)))
		self.assertEqual([c["animal"] for c in si.candidate_sires(self.cow.name, self.conceived)], [old_enough.name])
		self.assertTrue(young)

	def test_window_edges(self):
		window = frappe.db.get_single_value("Livestock Settings", "conception_window_days")
		# arrives the day after the window closes: not a candidate
		late = self._bull(self.other)
		move_animal(late.name, self.group, add_days(self.conceived, window + 1))
		# arrives on the last day of the window: a candidate
		edge = self._bull(self.other)
		move_animal(edge.name, self.group, add_days(self.conceived, window))
		# left the day before the window opens: not a candidate; left on its first day: he was gone
		early = self._bull(self.group)
		move_animal(early.name, self.other, add_days(self.conceived, -window))
		got = [c["animal"] for c in si.candidate_sires(self.cow.name, self.conceived)]
		self.assertEqual(got, [edge.name])

	def test_a_bull_in_another_herd_is_not_a_candidate(self):
		self._bull(self.other)
		self.assertEqual(si.candidate_sires(self.cow.name, self.conceived), [])

	def test_rotation_uses_the_herd_at_conception(self):
		bull = self._bull(self.other)
		move_animal(bull.name, self.group, ago(50))   # arrived after conception window
		self.assertEqual(si.candidate_sires(self.cow.name, self.conceived), [])
		self.assertEqual([c["animal"] for c in si.candidate_sires(self.cow.name, ago(40))], [bull.name])
