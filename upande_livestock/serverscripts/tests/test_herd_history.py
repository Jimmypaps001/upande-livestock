# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Herd history is rebuilt from Movement events."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from upande_livestock.serverscripts.common import herd_history as hh
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, move_animal


class TestHerdHistory(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.a = make_herd("ZZ HH A").name
		self.b = make_herd("ZZ HH B").name
		self.c = make_herd("ZZ HH C").name

	def test_never_moved_animal_is_in_its_birth_herd(self):
		cow = make_animal(self.a, sex="Female", date_of_birth=add_days(today(), -400))
		self.assertEqual(hh.herd_on(cow.name, today()), self.a)
		self.assertEqual(hh.herd_on(cow.name, add_days(today(), -399)), self.a)
		# not on the farm before it was born
		self.assertIsNone(hh.herd_on(cow.name, add_days(today(), -401)))

	def test_spans_from_movements_and_arrival_day_counts_in_new_herd(self):
		cow = make_animal(self.a, sex="Female", date_of_birth=add_days(today(), -400))
		move_animal(cow.name, self.b, add_days(today(), -100))
		move_animal(cow.name, self.c, add_days(today(), -10))
		self.assertEqual(hh.herd_on(cow.name, add_days(today(), -101)), self.a)
		self.assertEqual(hh.herd_on(cow.name, add_days(today(), -100)), self.b)
		self.assertEqual(hh.herd_on(cow.name, add_days(today(), -11)), self.b)
		self.assertEqual(hh.herd_on(cow.name, add_days(today(), -10)), self.c)
		self.assertEqual([s[0] for s in hh.spans(cow.name)], [self.a, self.b, self.c])
		self.assertIsNone(hh.spans(cow.name)[-1][2])

	def test_members_on_a_date(self):
		x = make_animal(self.a, date_of_birth=add_days(today(), -400))
		y = make_animal(self.b, date_of_birth=add_days(today(), -400))
		move_animal(x.name, self.b, add_days(today(), -30))
		self.assertEqual(hh.members_on(self.a, add_days(today(), -31)), [x.name])
		self.assertEqual(hh.members_on(self.a, add_days(today(), -30)), [])
		self.assertEqual(sorted(hh.members_on(self.b, add_days(today(), -30))), sorted([x.name, y.name]))

	def test_present_between_clips_to_the_window(self):
		x = make_animal(self.a, date_of_birth=add_days(today(), -400))
		move_animal(x.name, self.b, add_days(today(), -30))
		got = hh.present_between(self.a, add_days(today(), -40), add_days(today(), -20))
		self.assertEqual(got[x.name], (getdate(add_days(today(), -40)), getdate(add_days(today(), -31))))
		self.assertEqual(hh.present_between(self.a, add_days(today(), -20), today()), {})
