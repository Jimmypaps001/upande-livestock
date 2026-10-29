# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Moving a bull into a breeding herd is the decision to keep him: it needs his note."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.movement.create_movement_event import create_movement_event
from upande_livestock.serverscripts.movement.move_animals import move_animals
from upande_livestock.serverscripts.tests.beef_fixtures import (
	isolate, make_animal, make_herd, test_employee,
)

NOTE = "Strong Boran bull calf, good conformation, sire proven"


def ago(days):
	return add_days(today(), -days)


class TestSelectionMove(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.op = test_employee()
		self.calves = make_herd("ZZ Sel Calves", "Calf").name
		self.feedlot = make_herd("ZZ Sel Starters", "Fattening", 0, 250).name
		self.breeders = make_herd("ZZ Sel Bulls", "Breeding").name
		self.bull = make_animal(self.calves, sex="Male", date_of_birth=ago(220))

	def _refused(self, animal, herd, remarks=None):
		"""The move through the event itself: a refusal raises and leaves the test's rows alone."""
		doc = frappe.get_doc({
			"doctype": "Livestock Event", "event_type": "Movement", "animal": animal.name,
			"event_date": today(), "new_herd": herd, "operator": self.op, "remarks": remarks})
		before = frappe.db.get_value("Animal", animal.name, "current_herd")
		with self.assertRaises(frappe.MandatoryError) as caught:
			doc.insert(ignore_permissions=True)
		self.assertIn("Describe the bull", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Animal", animal.name, "current_herd"), before)

	def _move(self, animal, herd, remarks=None):
		return create_movement_event({
			"animal": animal.name, "new_herd": herd, "operator": self.op, "remarks": remarks})

	def test_male_into_breeding_without_a_note_is_refused(self):
		self._refused(self.bull, self.breeders)

	def test_a_short_note_is_refused(self):
		self._refused(self.bull, self.breeders, "good bull")

	def test_note_sets_the_stream_and_is_copied(self):
		got = self._move(self.bull, self.breeders, NOTE)
		self.assertTrue(got.get("ok"), got)
		row = frappe.db.get_value("Animal", self.bull.name,
		                          ["stream", "breeding_note", "breeding_note_by", "breeding_note_on", "current_herd"],
		                          as_dict=True)
		self.assertEqual((row.stream, row.breeding_note, row.breeding_note_by, str(row.breeding_note_on)),
		                 ("Breeding", NOTE, self.op, today()))
		self.assertEqual(row.current_herd, self.breeders)

	def test_into_a_fattening_herd_sets_the_feedlot_stream_without_a_note(self):
		got = self._move(self.bull, self.feedlot)
		self.assertTrue(got.get("ok"), got)
		self.assertEqual(frappe.db.get_value("Animal", self.bull.name, "stream"), "Feedlot")

	def test_a_feedlot_bull_can_be_selected_later_with_a_note(self):
		self._move(self.bull, self.feedlot)
		self._refused(self.bull, self.breeders)
		self.assertTrue(self._move(self.bull, self.breeders, NOTE).get("ok"))
		self.assertEqual(frappe.db.get_value("Animal", self.bull.name, "stream"), "Breeding")

	def test_a_heifer_never_needs_a_note(self):
		heifer = make_animal(self.calves, sex="Female", date_of_birth=ago(220))
		self.assertTrue(self._move(heifer, self.breeders).get("ok"))
		self.assertFalse(frappe.db.get_value("Animal", heifer.name, "stream"))

	def test_a_mature_bull_rotating_between_mating_groups_needs_no_note(self):
		other = make_herd("ZZ Sel Group 2", "Breeding").name
		bull = make_animal(self.breeders, sex="Male", date_of_birth=ago(2000), stream="Breeding")
		self.assertTrue(self._move(bull, other).get("ok"))

	def test_a_young_bull_leaving_his_dams_breeding_herd_for_the_reserve_needs_a_note(self):
		dams = make_herd("ZZ Sel Dams", "Breeding").name
		calf = make_animal(dams, sex="Male", date_of_birth=ago(230))
		self._refused(calf, self.breeders)
		self.assertTrue(self._move(calf, self.breeders, NOTE).get("ok"))

	def test_move_animals_needs_one_note_per_selected_bull(self):
		other = make_animal(self.calves, sex="Male", date_of_birth=ago(230))
		got = move_animals({"animals": [self.bull.name, other.name], "new_herd": self.breeders,
		                    "operator": self.op, "remarks_by_animal": {self.bull.name: NOTE}})
		self.assertIn(other.name, got["error"])
