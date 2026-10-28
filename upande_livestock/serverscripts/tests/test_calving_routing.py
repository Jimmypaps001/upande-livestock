# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where the dam and her calves stand once she has calved.

The calves are routed by sex. The dam goes to Livestock Settings' cow herd when
one is set, and stays where she is when none is.

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
from upande_livestock.serverscripts.tests.beef_fixtures import make_herd
from upande_livestock.serverscripts.tests.test_employee_gate import link_employee
from upande_livestock.serverscripts.tests.timings_utils import set_setting
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_open_backdating_window,
	_purge,
	_purge_events_for,
)


def _employee():
	"""An active Employee, made inside the test when the site has none, so the
	end-to-end tests run on an empty site instead of skipping."""
	found = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	if not found:
		link_employee("zz-calving@example.com")
		found = frappe.db.get_value("Employee", {"user_id": "zz-calving@example.com"}, "name")
	return found


def _forget_fixtures():
	"""Take back the Employee and herds the helpers above made, if they did."""
	frappe.db.delete("Employee", {"user_id": "zz-calving@example.com"})
	for name in frappe.get_all("Herds", filters={"herd_name": ["like", "ZZ Calving Herd %"]}, pluck="name"):
		frappe.db.delete("Herds", {"name": name})
	frappe.db.commit()


def _two_herds():
	"""Two herds, made inside the test when the site has fewer than two."""
	herds = frappe.get_all("Herds", pluck="name", limit_page_length=2, order_by="name")
	for n in range(2 - len(herds)):
		herds.append(make_herd(f"ZZ Calving Herd {n}").name)
	return herds


class TestTheDestinationsAreAnsweredBeforeAnythingIsWritten(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(_forget_fixtures)
		self.addCleanup(_purge, "Animal", "ZZ DESTINATION DAM")
		herd = _two_herds()[0]
		self.dam = _make_cow("ZZ DESTINATION DAM", months_old=48, herd=herd).name

	def test_it_names_all_three_destinations(self):
		got = calving_destinations(dam=self.dam)
		self.assertTrue(got.get("ok"), got.get("error"))
		for who in ("dam", "female_calf", "male_calf"):
			self.assertIn(who, got)

	def test_the_dam_stays_where_she_is_with_no_cow_herd(self):
		set_setting(self, "cow_herd", None)
		got = calving_destinations(dam=self.dam)
		self.assertFalse(got["dam"]["will_move"])
		self.assertEqual(got["dam"]["from_herd"], got["dam"]["to_herd"])

	def test_the_two_sexes_do_not_share_a_destination(self):
		got = calving_destinations(dam=self.dam)
		if not (got["female_calf"]["to_herd"] and got["male_calf"]["to_herd"]):
			raise unittest.SkipTest("calf herds are not set on this site")
		self.assertNotEqual(got["female_calf"]["to_herd"], got["male_calf"]["to_herd"])

	def test_asking_changes_nothing(self):
		"""It is a question, not the first half of the answer."""
		before = frappe.db.get_value("Animal", self.dam, "current_herd")
		calving_destinations(dam=self.dam)
		self.assertEqual(frappe.db.get_value("Animal", self.dam, "current_herd"), before)

	def test_it_refuses_without_a_dam(self):
		self.assertIn("error", calving_destinations(dam=None))


class TestTheDamAfterCalving(IntegrationTestCase):
	def setUp(self):
		_open_backdating_window(self)
		self.addCleanup(_forget_fixtures)
		self.employee = _employee()
		if not self.employee:
			raise unittest.SkipTest("no active Employee on this site")
		self.herd, self.cows = _two_herds()

		self.dam = _make_cow("ZZ ROUTING DAM", months_old=48, herd=self.herd)
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

	def _calve(self, when=None):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Calving"
		doc.animal = self.dam.name
		doc.event_date = when or today()
		doc.operator = self.employee
		doc.custom_no_of_calves = 1
		doc.custom_calving_outcome = "Live Birth"
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _herd_of_dam(self):
		return frappe.db.get_value("Animal", self.dam.name, "current_herd")

	def test_with_no_cow_herd_she_stays_put(self):
		set_setting(self, "cow_herd", None)
		self._calve()
		self.assertEqual(self._herd_of_dam(), self.herd)
		self.assertFalse(frappe.db.exists("Livestock Event", {
			"animal": self.dam.name, "event_type": "Movement", "docstatus": 1}))

	def test_with_a_cow_herd_she_moves_there_and_can_be_served_again(self):
		set_setting(self, "cow_herd", self.cows)
		self._calve()
		self.assertEqual(self._herd_of_dam(), self.cows)
		self.assertIn(self.cows, hm.service_herds())
		wait = hm.service_wait_days()
		frappe.db.set_value("Animal", self.dam.name, "last_calving_date",
		                    add_days(today(), -(wait + 1)), update_modified=False)
		frappe.clear_document_cache("Animal", self.dam.name)
		self.assertTrue(hm.is_servable(self.dam.name))

	def test_a_cow_who_moved_since_is_left_where_she_stands(self):
		set_setting(self, "cow_herd", self.cows)
		move = frappe.new_doc("Livestock Event")
		move.event_type = "Movement"
		move.animal = self.dam.name
		move.event_date = today()
		move.new_herd = self.cows
		move.operator = self.employee
		move.insert(ignore_permissions=True)
		move.submit()
		self._calve(when=add_days(today(), -30))
		self.assertEqual(self._herd_of_dam(), self.cows)
		self.assertEqual(frappe.db.count("Livestock Event", {
			"animal": self.dam.name, "event_type": "Movement", "docstatus": 1}), 1)


class TestAnAnimalWithNoHerdCanBeMovedIntoOne(IntegrationTestCase):
	"""A regression: validate() runs twice — at insert and again at submit — and
	the herd movement processor lives inside it. On the second pass the animal
	had already been moved, so current_herd was re-read as the destination and
	the "cannot be the same" guard fired. An animal that started with no herd
	could be inserted into a Movement and never submitted.
	"""

	def setUp(self):
		self.tag = "ZZ HERDLESS MOVE"
		self.addCleanup(_forget_fixtures)
		self.addCleanup(_purge_events_for, self.tag)
		self.addCleanup(_purge, "Animal", self.tag)
		_purge("Animal", self.tag)
		self.destination = _two_herds()[0]
		self.animal = frappe.get_doc({
			"doctype": "Animal", "tag_number": self.tag, "burn_name": self.tag,
			"sex": "Female", "status": "Active",
			"date_of_birth": add_days(today(), -900), "current_herd": None,
		}).insert(ignore_permissions=True)

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
	"""Cancelling a move used to leave the animal where the move had put her."""

	def setUp(self):
		self.tag = "ZZ UNDO MOVE"
		self.addCleanup(_purge_events_for, self.tag)
		self.addCleanup(_purge, "Animal", self.tag)
		_purge("Animal", self.tag)
		self.addCleanup(_forget_fixtures)
		self.employee = _employee()
		if not self.employee:
			raise unittest.SkipTest("no active Employee on this site")
		self.origin, self.destination = _two_herds()
		frappe.get_doc({
			"doctype": "Animal", "tag_number": self.tag, "burn_name": self.tag,
			"sex": "Female", "status": "Active",
			"date_of_birth": add_days(today(), -1400), "current_herd": self.origin,
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
		self.assertEqual(frappe.db.get_value("Animal", self.tag, "current_herd"), self.origin)

	def test_both_headcounts_come_back_with_her(self):
		before = frappe.db.get_value("Herds", self.origin, "number_of_animals")
		move = self._move(self.destination)
		self.assertEqual(frappe.db.get_value("Herds", self.origin, "number_of_animals"), before - 1)
		move.cancel()
		self.assertEqual(frappe.db.get_value("Herds", self.origin, "number_of_animals"), before)


class TestTheManufactureQuantityIsRoundedOnce(IntegrationTestCase):
	"""A head count that is exact in decimal and not in binary.

	87 head at a twentieth of a ration is 4.3500000000000005. The Work Order
	stored 4.35 and the Stock Entry was built from the raw value, so ERPNext
	refused it: "For quantity 4.35 should not be greater than allowed quantity
	4.35". Both numbers print the same, and one of them really is bigger.

	A herd of 111 head — also inexact — is an ordinary size, so this is not a
	corner case that needed a contrived herd to reach.
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
