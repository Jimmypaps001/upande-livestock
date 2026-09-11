# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where the dam and her calves stand once she has calved.

Three animals change herd at a calving and, until now, two of them did. The
calves were routed by sex; the cow stayed in the dry herd she calved in,
because nothing moved her. She was milking and the system had her standing
with the steamers.

The destinations are also answered BEFORE anything is written, so the person
at the pen can see the consequence while they can still say it is wrong.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.breeding.calving_destinations import calving_destinations
from upande_livestock.serverscripts.breeding.create_service_event import create_service_event
from upande_livestock.serverscripts.common import herd_movement as hm
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_open_backdating_window,
	_purge,
	_purge_events_for,
)


def _employee():
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


class TestTheDestinationsAreAnsweredBeforeAnythingIsWritten(IntegrationTestCase):
	def setUp(self):
		self.dam = frappe.db.get_value(
			"Animal", {"current_herd": "STEAMERS", "status": "Active", "disabled": 0}, "name")
		if not self.dam:
			raise unittest.SkipTest("no dry cow on this site")

	def test_it_names_all_three_destinations(self):
		got = calving_destinations(dam=self.dam)
		self.assertTrue(got.get("ok"), got.get("error"))
		for who in ("dam", "female_calf", "male_calf"):
			self.assertIn(who, got)
			self.assertTrue(got[who].get("to_herd"), "{} has nowhere to go".format(who))

	def test_the_two_sexes_do_not_share_a_destination(self):
		got = calving_destinations(dam=self.dam)
		self.assertNotEqual(got["female_calf"]["to_herd"], got["male_calf"]["to_herd"])

	def test_a_dry_cow_is_told_she_will_move(self):
		got = calving_destinations(dam=self.dam)
		self.assertTrue(got["dam"]["will_move"])
		self.assertEqual(got["dam"]["from_herd"], "STEAMERS")
		self.assertEqual(got["dam"]["to_herd"], hm.post_calving_herd())

	def test_a_cow_already_milking_is_told_she_will_not(self):
		milking = frappe.db.get_value(
			"Animal", {"current_herd": hm.post_calving_herd(), "status": "Active"}, "name")
		if not milking:
			raise unittest.SkipTest("nobody in the post-calving herd")
		got = calving_destinations(dam=milking)
		self.assertFalse(got["dam"]["will_move"])
		self.assertIn("already", got["dam"]["reason"])

	def test_asking_changes_nothing(self):
		"""It is a question, not the first half of the answer."""
		before = frappe.db.get_value("Animal", self.dam, "current_herd")
		calving_destinations(dam=self.dam)
		self.assertEqual(frappe.db.get_value("Animal", self.dam, "current_herd"), before)

	def test_it_refuses_without_a_dam(self):
		self.assertIn("error", calving_destinations(dam=None))


class TestTheDamActuallyMoves(IntegrationTestCase):
	"""The part that was missing entirely."""

	def setUp(self):
		_open_backdating_window(self)
		self.employee = _employee()
		if not self.employee:
			raise unittest.SkipTest("no active Employee on this site")
		self.destination = hm.post_calving_herd()
		if not self.destination:
			raise unittest.SkipTest("no post-calving herd configured")

		self.dam = _make_cow("ZZ ROUTING DAM", months_old=48, herd="STEAMERS")
		self.addCleanup(_purge_events_for, self.dam.name)
		self.addCleanup(_purge, "Animal", self.dam.name)

		served = add_days(today(), -285)
		r = create_service_event({
			"animal": self.dam.name, "service_type": "A.I.",
			"service_date": served, "operator": self.employee,
		})
		if r.get("error"):
			raise unittest.SkipTest("could not record a service: {}".format(r["error"][:120]))
		dx = frappe.new_doc("Livestock Event")
		dx.event_type = "Pregnancy Diagnosis"
		dx.animal = self.dam.name
		dx.event_date = add_days(served, 60)
		dx.operator = self.employee
		dx.diagnosis_result = "Confirmed"
		dx.related_service = r["name"]
		dx.insert(ignore_permissions=True)
		dx.submit()
		self.service = r["name"]

	def _calve(self, when=None):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Calving"
		doc.animal = self.dam.name
		doc.event_date = when or today()
		doc.operator = self.employee
		doc.custom_no_of_calves = 1
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_she_leaves_the_dry_herd(self):
		self.assertEqual(self.dam.current_herd, "STEAMERS")
		self._calve()
		self.assertEqual(
			frappe.db.get_value("Animal", self.dam.name, "current_herd"), self.destination,
			"a cow that has calved is milking, and belongs with the milking herd")

	def test_the_move_is_recorded_as_a_movement_not_a_field_write(self):
		"""days_in_current_herd measures from the last Movement into a herd, and
		the dry period in Steamers is decided by the herd she arrived from. A cow
		teleported by a field write has no arrival at all."""
		self._calve()
		move = frappe.get_all(
			"Livestock Event",
			filters={"animal": self.dam.name, "event_type": "Movement",
			         "new_herd": self.destination, "docstatus": 1},
			fields=["name", "event_date", "remarks"])
		self.assertEqual(len(move), 1, "the calving left no movement behind")
		self.assertIn("Calved", move[0].remarks or "")

	def test_the_move_carries_the_calving_date_not_todays(self):
		when = add_days(today(), -3)
		self._calve(when=when)
		move = frappe.get_all(
			"Livestock Event",
			filters={"animal": self.dam.name, "event_type": "Movement", "docstatus": 1},
			fields=["event_date"])[0]
		self.assertEqual(str(move.event_date), str(when))

	def test_the_headcounts_follow_her(self):
		before_from = frappe.db.get_value("Herds", "STEAMERS", "number_of_animals")
		before_to = frappe.db.get_value("Herds", self.destination, "number_of_animals")
		self._calve()
		self.assertEqual(
			frappe.db.get_value("Herds", "STEAMERS", "number_of_animals"), before_from - 1)
		self.assertEqual(
			frappe.db.get_value("Herds", self.destination, "number_of_animals"), before_to + 1)

	def test_a_cow_who_moved_since_is_left_where_she_stands(self):
		"""Backdating a calving from months back must not drag a cow out of the
		herd she is standing in today — she may have been served, confirmed and
		dried off again since."""
		move = frappe.new_doc("Livestock Event")
		move.event_type = "Movement"
		move.animal = self.dam.name
		move.event_date = today()
		move.new_herd = "INCALF HEIFERS"
		move.operator = self.employee
		move.insert(ignore_permissions=True)
		move.submit()

		self._calve(when=add_days(today(), -30))
		self.assertEqual(
			frappe.db.get_value("Animal", self.dam.name, "current_herd"), "INCALF HEIFERS",
			"a later move outranks a backdated calving")


class TestAnAnimalWithNoHerdCanBeMovedIntoOne(IntegrationTestCase):
	"""A regression, found by the calving move and older than it.

	validate() runs twice — at insert and again at submit — and the herd
	movement processor lives inside it. On the second pass the animal had
	already been moved, so current_herd was re-read as the destination and the
	"cannot be the same" guard fired. An animal that started with no herd could
	be inserted into a Movement and never submitted.
	"""

	def setUp(self):
		self.tag = "ZZ HERDLESS MOVE"
		self.addCleanup(_purge_events_for, self.tag)
		self.addCleanup(_purge, "Animal", self.tag)
		_purge("Animal", self.tag)
		self.animal = frappe.get_doc({
			"doctype": "Animal", "tag_number": self.tag, "burn_name": self.tag,
			"sex": "Female", "status": "Active",
			"date_of_birth": add_days(today(), -900), "current_herd": None,
		}).insert(ignore_permissions=True)
		self.destination = hm.post_calving_herd()
		if not self.destination:
			raise unittest.SkipTest("no destination herd configured")

	def test_it_can_be_moved_through_the_endpoint(self):
		from upande_livestock.serverscripts.movement.create_movement_event import (
			create_movement_event,
		)
		employee = _employee()
		if not employee:
			raise unittest.SkipTest("no active Employee on this site")
		res = create_movement_event({
			"animal": self.tag, "new_herd": self.destination, "event_date": today(),
			"operator": employee,
		})
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(
			frappe.db.get_value("Animal", self.tag, "current_herd"), self.destination)

	def test_an_animal_already_in_the_herd_is_still_refused(self):
		"""The guard itself was right; only its input was stale."""
		frappe.db.set_value("Animal", self.tag, "current_herd", self.destination)
		move = frappe.new_doc("Livestock Event")
		move.event_type = "Movement"
		move.animal = self.tag
		move.event_date = today()
		move.new_herd = self.destination
		with self.assertRaises(frappe.ValidationError):
			move.insert(ignore_permissions=True)


class TestCancellingTheMoveUndoesIt(IntegrationTestCase):
	"""Cancelling a move used to leave the animal where the move had put her.

	That was survivable while every move was typed by a person. Now a calving
	makes one on its own, so a calving entered against the wrong cow has to be
	undoable — and undoing it has to put her back in the dry herd.
	"""

	def setUp(self):
		self.tag = "ZZ UNDO MOVE"
		self.addCleanup(_purge_events_for, self.tag)
		self.addCleanup(_purge, "Animal", self.tag)
		_purge("Animal", self.tag)
		self.employee = _employee()
		if not self.employee:
			raise unittest.SkipTest("no active Employee on this site")
		self.destination = hm.post_calving_herd()
		if not self.destination:
			raise unittest.SkipTest("no destination herd configured")
		frappe.get_doc({
			"doctype": "Animal", "tag_number": self.tag, "burn_name": self.tag,
			"sex": "Female", "status": "Active",
			"date_of_birth": add_days(today(), -1400), "current_herd": "STEAMERS",
		}).insert(ignore_permissions=True)

	def _move(self, to_herd):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Movement"
		doc.animal = self.tag
		doc.event_date = today()
		doc.new_herd = to_herd
		doc.operator = self.employee
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_she_goes_back_where_she_came_from(self):
		move = self._move(self.destination)
		self.assertEqual(frappe.db.get_value("Animal", self.tag, "current_herd"), self.destination)
		move.cancel()
		self.assertEqual(frappe.db.get_value("Animal", self.tag, "current_herd"), "STEAMERS")

	def test_both_headcounts_come_back_with_her(self):
		before = frappe.db.get_value("Herds", "STEAMERS", "number_of_animals")
		move = self._move(self.destination)
		self.assertEqual(frappe.db.get_value("Herds", "STEAMERS", "number_of_animals"), before - 1)
		move.cancel()
		self.assertEqual(frappe.db.get_value("Herds", "STEAMERS", "number_of_animals"), before)

	def test_a_later_move_is_not_undone_by_cancelling_an_earlier_one(self):
		"""Cancelling the first move must not drag her out of where the second
		one put her — that would undo the second move, not the first."""
		first = self._move(self.destination)
		self._move("INCALF HEIFERS")
		first.cancel()
		self.assertEqual(
			frappe.db.get_value("Animal", self.tag, "current_herd"), "INCALF HEIFERS")


class TestTheManufactureQuantityIsRoundedOnce(IntegrationTestCase):
	"""A head count that is exact in decimal and not in binary.

	87 head at a twentieth of a ration is 4.3500000000000005. The Work Order
	stored 4.35 and the Stock Entry was built from the raw value, so ERPNext
	refused it: "For quantity 4.35 should not be greater than allowed quantity
	4.35". Both numbers print the same, and one of them really is bigger.

	Lactating Group 1 stood at 111 head — also inexact — for months, so this is
	not a corner case that needed a contrived herd to reach.
	"""

	def test_the_head_counts_that_break_in_binary_come_back_exact(self):
		from upande_livestock.serverscripts.feeding._engine import manufacture_qty

		for heads in (87, 111):
			raw = 1.0 * heads * 0.05
			self.assertGreater(raw, round(raw, 6), "{} was supposed to be inexact".format(heads))
			self.assertEqual(manufacture_qty(1.0, heads, 0.05), round(raw, 6))

	def test_the_exact_ones_are_left_alone(self):
		from upande_livestock.serverscripts.feeding._engine import manufacture_qty

		for heads in (86, 88, 100):
			self.assertEqual(manufacture_qty(1.0, heads, 0.05), 1.0 * heads * 0.05)

	def test_no_portion_means_the_whole_ration(self):
		from upande_livestock.serverscripts.feeding._engine import manufacture_qty

		self.assertEqual(manufacture_qty(2.0, 10), 20.0)
		self.assertEqual(manufacture_qty(2.0, 10, 0), 20.0)
