# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Marking a cow for cull review, and putting it in her history.

A JUDGEMENT, NOT A DISPOSAL. She keeps her herd, her place in the head count
and her ration; nothing about the farm's arithmetic changes. Culling her is a
Livestock Disposal, a different act with a different permission.

The history entry is the part that had never worked. It was written as a "Check
Up" for want of a type of its own — a health record on her timeline for a
decision about her productivity — and it was wrapped in a bare `except` that
swallowed the MandatoryError every call raised, because a Livestock Event needs
an Employee and most users have none linked. The mark was made and the timeline
never showed it, silently, for as long as the feature existed.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.animals.mark_cull_review import (
	EVENT_TYPE,
	mark_cull_review,
)
from upande_livestock.serverscripts.tests.test_culling import _employee


class TestMarkingACowForReview(IntegrationTestCase):
	def setUp(self):
		self.animal = frappe.db.get_value(
			"Animal", {"disabled": 0, "sex": "Female", "custom_cull_candidate": 0}, "name")
		if not self.animal:
			self.skipTest("no unmarked female on this site")
		self.addCleanup(self._clear)

	def _clear(self):
		frappe.set_user("Administrator")
		mark_cull_review({"animal": self.animal, "marked": False, "operator": _employee()})
		for name in frappe.get_all(
			"Livestock Event", filters={"animal": self.animal, "event_type": EVENT_TYPE},
			pluck="name",
		):
			doc = frappe.get_doc("Livestock Event", name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Livestock Event", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_the_mark_lands_on_her_record_with_its_reason(self):
		got = mark_cull_review({
			"animal": self.animal, "reason": "Third mastitis this lactation",
			"operator": _employee(),
		})
		self.assertTrue(got.get("ok"), got.get("error"))
		row = frappe.db.get_value(
			"Animal", self.animal,
			["custom_cull_candidate", "custom_cull_reason", "custom_cull_marked_by"],
			as_dict=True)
		self.assertEqual(row.custom_cull_candidate, 1)
		self.assertEqual(row.custom_cull_reason, "Third mastitis this lactation")
		self.assertEqual(row.custom_cull_marked_by, frappe.session.user)

	def test_the_decision_reaches_her_timeline_under_its_own_type(self):
		"""Not as a Check Up. A health record for a productivity decision is the
		wrong thing for the next person reading her history to find."""
		got = mark_cull_review({
			"animal": self.animal, "reason": "Below the herd on every measure",
			"operator": _employee(),
		})
		self.assertTrue(got["timeline"], "the mark was not written to her history")
		event = frappe.db.get_value(
			"Livestock Event", {"animal": self.animal, "event_type": EVENT_TYPE},
			["remarks", "event_type"], as_dict=True)
		self.assertIsNotNone(event)
		self.assertIn("Below the herd", event.remarks)

	def test_it_says_so_when_the_history_cannot_be_written(self):
		"""The failure that hid for the life of the feature. The mark still
		lands — it is the thing that matters — but nobody is left believing the
		timeline shows it."""
		got = mark_cull_review({"animal": self.animal, "reason": "No employee here"})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertFalse(got["timeline"])
		self.assertEqual(
			frappe.db.get_value("Animal", self.animal, "custom_cull_candidate"), 1)

	def test_taking_the_mark_off_records_that_too(self):
		mark_cull_review({"animal": self.animal, "reason": "worth a look",
		                  "operator": _employee()})
		got = mark_cull_review({"animal": self.animal, "marked": False,
		                        "operator": _employee()})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertFalse(frappe.db.get_value("Animal", self.animal, "custom_cull_candidate"))
		remarks = frappe.get_all(
			"Livestock Event", filters={"animal": self.animal, "event_type": EVENT_TYPE},
			pluck="remarks")
		self.assertIn("Cull review mark removed", remarks)

	def test_a_mark_with_no_case_behind_it_is_refused(self):
		"""One nobody can review is one nobody will."""
		got = mark_cull_review({"animal": self.animal, "operator": _employee()})
		self.assertIn("Say why", got.get("error", ""))

	def test_she_keeps_her_herd_and_her_place_in_the_count(self):
		"""A judgement, not a disposal."""
		herd = frappe.db.get_value("Animal", self.animal, "current_herd")
		before = frappe.db.get_value("Herds", herd, "number_of_animals") if herd else None
		mark_cull_review({"animal": self.animal, "reason": "worth a look",
		                  "operator": _employee()})
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "current_herd"), herd)
		if herd:
			self.assertEqual(
				frappe.db.get_value("Herds", herd, "number_of_animals"), before)
		self.assertFalse(frappe.db.get_value("Animal", self.animal, "disabled"))
