# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A round skips the animals a rule refuses; it does not fail for them.

One cow dewormed last week used to refuse the whole herd's round. Each animal
is now judged on her own: the eligible ones are recorded and charged to the
store, the others come back as `skipped` with the rule's reason, and a round
with nobody eligible is an error that lists why.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from upande_livestock.serverscripts.husbandry.create_husbandry_event import create_husbandry_event
from upande_livestock.serverscripts.husbandry.round_eligibility import round_eligibility
from upande_livestock.serverscripts.tests.test_drug_issuing import _drug_store, _stocked_drug
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge, _purge_events_for


class TestARoundSkipsWhoCannotHaveIt(IntegrationTestCase):
	TAGS = ("ZZ SKIP COW 1", "ZZ SKIP COW 2", "ZZ SKIP COW 3")

	def setUp(self):
		self.drug = _stocked_drug(min_qty=3)
		if not self.drug:
			raise unittest.SkipTest("no drug with enough stock on this site")
		self.who = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		self.cows = [_make_cow(tag) for tag in self.TAGS]
		for cow in self.cows:
			self.addCleanup(_purge_events_for, cow.name)
			self.addCleanup(_purge, "Animal", cow.name)
		# Cow 1 was dewormed already: inside the interval, so she is ineligible.
		first = create_husbandry_event(
			{"event_type": "Deworming", "animals": [self.TAGS[0]], "event_date": today(), "operator": self.who}
		)
		self.assertTrue(first.get("ok"), first)

	def _bal(self):
		return flt(
			frappe.db.get_value("Bin", {"item_code": self.drug.item_code, "warehouse": _drug_store()}, "actual_qty")
		)

	def _round(self, animals, **kw):
		payload = {
			"event_type": "Deworming", "animals": animals, "event_date": today(), "operator": self.who,
			"drugs": [{"item_code": self.drug.item_code, "qty": 1}],
		}
		payload.update(kw)
		return create_husbandry_event(payload)

	def test_a_mixed_round_records_the_eligible_and_reports_the_rest(self):
		got = self._round(list(self.TAGS))
		self.assertTrue(got.get("ok"), got)
		for name in got["names"]:
			self.addCleanup(_purge, "Livestock Event", name)
		if got.get("stock_entry"):
			self.addCleanup(_purge, "Stock Entry", got["stock_entry"])
		self.assertEqual(got["recorded"], [self.TAGS[1], self.TAGS[2]])
		self.assertEqual([s["animal"] for s in got["skipped"]], [self.TAGS[0]])
		self.assertTrue(got["skipped"][0]["reason"])
		self.assertEqual(got["animals"], 2)

	def test_stock_is_issued_only_for_the_recorded(self):
		before = self._bal()
		got = self._round(list(self.TAGS))
		self.assertTrue(got.get("ok"), got)
		for name in got["names"]:
			self.addCleanup(_purge, "Livestock Event", name)
		self.addCleanup(_purge, "Stock Entry", got["stock_entry"])
		se = frappe.get_doc("Stock Entry", got["stock_entry"])
		self.assertEqual(flt(se.items[0].qty), 2)
		self.assertAlmostEqual(before - self._bal(), 2, places=4)

	def test_a_round_nobody_can_have_is_an_error_listing_why(self):
		before = self._bal()
		got = self._round([self.TAGS[0]])
		self.assertIn("error", got)
		self.assertIn(self.TAGS[0], got["error"])
		self.assertAlmostEqual(before, self._bal(), places=4)

	def test_the_preview_marks_the_same_animals_without_recording(self):
		got = round_eligibility(
			{"event_type": "Deworming", "animals": list(self.TAGS), "event_date": today()}
		)
		self.assertTrue(got.get("ok"), got)
		self.assertEqual(got["eligible"], [self.TAGS[1], self.TAGS[2]])
		self.assertEqual([s["animal"] for s in got["skipped"]], [self.TAGS[0]])
		self.assertEqual(
			frappe.db.count("Livestock Event", {"animal": self.TAGS[1], "docstatus": 1}), 0
		)
