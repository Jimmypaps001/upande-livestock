# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Moving a set of animals into one herd.

Nobody walks one cow across the yard and comes back for the next, so the batch
is the unit of work. Two rules make that safe:

ONE EVENT PER ANIMAL, not one for the batch. Her timeline has to answer where
she was in March on its own; a single record naming forty cows answers it for
none of them, and the head counts would have to be worked out by hand instead
of falling out of the movement processor.

THE WHOLE SET IS CHECKED BEFORE ANY OF IT MOVES. Forty animals picked off a
list is forty chances for one to have left the farm since the page loaded, and
a batch that moved thirty-nine and stopped would leave somebody reconciling
which.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.movement.move_animals import move_animals
from upande_livestock.serverscripts.tests.test_culling import _employee, _tidy
from upande_livestock.serverscripts.tests.test_operations import _make_cow

FROM_HERD, TO_HERD = "Lactating group 1", "STEAMERS"
COWS = ["MOVE-BATCH-1", "MOVE-BATCH-2", "MOVE-BATCH-3"]


class TestMovingASet(IntegrationTestCase):
	def setUp(self):
		for tag in COWS:
			_tidy(tag)
			_make_cow(tag, herd=FROM_HERD)
		frappe.db.commit()
		self.addCleanup(lambda: [_tidy(t) for t in COWS])

	def _move(self, animals, herd=TO_HERD, **kw):
		return move_animals({"animals": animals, "new_herd": herd,
		                     "operator": _employee(), **kw})

	def test_they_all_arrive(self):
		got = self._move(COWS)
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["count"], len(COWS))
		for tag in COWS:
			self.assertEqual(frappe.db.get_value("Animal", tag, "current_herd"), TO_HERD)

	def test_each_one_gets_her_own_event(self):
		"""A single record naming three cows answers "where was she" for none."""
		self._move(COWS)
		for tag in COWS:
			self.assertTrue(frappe.db.exists("Livestock Event", {
				"animal": tag, "event_type": "Movement", "new_herd": TO_HERD, "docstatus": 1}))

	def test_both_head_counts_follow(self):
		before_from = frappe.db.get_value("Herds", FROM_HERD, "number_of_animals")
		before_to = frappe.db.get_value("Herds", TO_HERD, "number_of_animals")
		self._move(COWS)
		self.assertEqual(
			frappe.db.get_value("Herds", FROM_HERD, "number_of_animals"),
			before_from - len(COWS))
		self.assertEqual(
			frappe.db.get_value("Herds", TO_HERD, "number_of_animals"),
			before_to + len(COWS))

	def test_one_bad_animal_stops_the_whole_batch(self):
		"""Thirty-nine moved and one refused is somebody reconciling which."""
		got = self._move([*COWS, "NO-SUCH-ANIMAL"])
		self.assertIn("not an animal", got.get("error", ""))
		for tag in COWS:
			self.assertEqual(frappe.db.get_value("Animal", tag, "current_herd"), FROM_HERD)

	def test_every_problem_is_named_at_once(self):
		got = self._move([COWS[0], COWS[0], "NO-SUCH-ANIMAL"])
		self.assertIn("twice", got.get("error", ""))
		self.assertIn("NO-SUCH-ANIMAL", got.get("error", ""))

	def test_an_animal_already_there_is_refused_rather_than_moved_again(self):
		"""A second Movement to the herd she is standing in is a row in her
		history that says nothing happened."""
		self._move(COWS)
		again = self._move(COWS)
		self.assertIn("already in", again.get("error", ""))

	def test_an_animal_that_has_left_the_farm_cannot_be_moved(self):
		frappe.db.set_value("Animal", COWS[0], {"disabled": 1, "status": "Sold"})
		got = self._move(COWS)
		self.assertIn("left the farm", got.get("error", ""))

	def test_an_empty_selection_is_refused(self):
		self.assertIn("at least one animal", self._move([]).get("error", ""))

	def test_a_herd_that_is_not_there_is_refused(self):
		got = self._move(COWS, herd="NO SUCH HERD")
		self.assertIn("not a herd", got.get("error", ""))
		self.assertEqual(
			frappe.db.get_value("Animal", COWS[0], "current_herd"), FROM_HERD)

	def test_the_reason_travels_with_every_one_of_them(self):
		self._move(COWS, remarks="Coming into milk")
		for tag in COWS:
			self.assertEqual(
				frappe.db.get_value(
					"Livestock Event",
					{"animal": tag, "event_type": "Movement", "new_herd": TO_HERD},
					"remarks"),
				"Coming into milk")
