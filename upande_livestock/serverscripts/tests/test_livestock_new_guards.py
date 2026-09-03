# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Tests for the two guards added alongside the husbandry work.

Both close gaps that were previously browser-only or absent entirely, so each test
exercises the guard through a server-side insert — the path the desk form's own
copy of the rule never covered.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.tests.test_operations import _employee, _make_cow, _purge, _purge_events_for


def _event(animal, event_type, event_date, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Livestock Event",
			"animal": animal,
			"event_type": event_type,
			"event_date": event_date,
			"operator": _employee(),
			**kwargs,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestDehorningAgeWindow(IntegrationTestCase):
	"""Dehorning has a 1-6 month window. It lived only in livestock_event.js, so
	every non-desk path walked past it."""

	def test_a_calf_inside_the_window_is_allowed(self):
		cow = _make_cow("ZZ GUARD DEHORN OK", months_old=3)
		self.addCleanup(_purge, "Animal", cow.name)
		self.addCleanup(_purge_events_for, cow.name)
		doc = _event(cow.name, "Dehorning", today())
		self.assertEqual(doc.event_type, "Dehorning")

	def test_too_young_is_rejected(self):
		cow = _make_cow("ZZ GUARD DEHORN YOUNG", months_old=0)
		self.addCleanup(_purge, "Animal", cow.name)
		self.addCleanup(_purge_events_for, cow.name)
		with self.assertRaises(frappe.ValidationError) as caught:
			_event(cow.name, "Dehorning", today())
		self.assertIn("too young", str(caught.exception).lower())

	def test_too_old_is_rejected(self):
		cow = _make_cow("ZZ GUARD DEHORN OLD", months_old=24)
		self.addCleanup(_purge, "Animal", cow.name)
		self.addCleanup(_purge_events_for, cow.name)
		with self.assertRaises(frappe.ValidationError) as caught:
			_event(cow.name, "Dehorning", today())
		self.assertIn("window", str(caught.exception).lower())

	def test_an_animal_with_no_date_of_birth_is_never_blocked(self):
		"""Plenty of purchased animals have no DOB; that must not stop recording."""
		cow = _make_cow("ZZ GUARD DEHORN NODOB")
		frappe.db.set_value("Animal", cow.name, "date_of_birth", None, update_modified=False)
		self.addCleanup(_purge, "Animal", cow.name)
		self.addCleanup(_purge_events_for, cow.name)
		doc = _event(cow.name, "Dehorning", today())
		self.assertEqual(doc.event_type, "Dehorning")


class TestDuplicateEventGuard(IntegrationTestCase):
	def setUp(self):
		self.cow = _make_cow("ZZ GUARD DUP COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)

	def test_a_second_same_day_drying_off_is_rejected(self):
		first = _event(self.cow.name, "Drying Off", today())
		first.submit()
		with self.assertRaises(frappe.DuplicateEntryError):
			_event(self.cow.name, "Drying Off", today())

	def test_a_different_day_is_fine(self):
		first = _event(self.cow.name, "Drying Off", add_days(today(), -10))
		first.submit()
		second = _event(self.cow.name, "Drying Off", today())
		self.assertEqual(second.event_type, "Drying Off")

	def test_an_unguarded_type_may_repeat_in_a_day(self):
		"""Vaccination is deliberately NOT guarded — several drugs in one visit is
		normal, and record_calf_births relies on Birth repeating too."""
		first = _event(self.cow.name, "Vaccination", today())
		first.submit()
		second = _event(self.cow.name, "Vaccination", today())
		self.assertEqual(second.event_type, "Vaccination")

	def test_a_draft_duplicate_does_not_block(self):
		"""Only a submitted event counts — a draft is not yet a record of anything."""
		_event(self.cow.name, "Drying Off", today())  # left in draft
		second = _event(self.cow.name, "Drying Off", today())
		self.assertEqual(second.event_type, "Drying Off")
