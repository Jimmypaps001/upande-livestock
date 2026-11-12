# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Breeding guards judge a record as of ITS date, and the Animal shows the newest event's state.

History is loaded after the fact: a Service dated last January goes in after the Calving
of last October. The guards used to look at every event the animal had, whatever its date,
so history could only be entered in the order it happened.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.upande_livestock.doctype.livestock_event.livestock_event import (
	recompute_repro_state,
)
from upande_livestock.upande_livestock.doctype.livestock_event.test_livestock_event import (
	IGNORE_TEST_RECORD_DEPENDENCIES,  # noqa: F401  (the runner reads it from this module)
	_delete_and_commit,
	make_animal,
	make_event,
)


class TestBreedingAsOf(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.cow = make_animal("TEST-ASOF-COW").name
		self.addCleanup(_delete_and_commit, "Animal", self.cow)
		self.addCleanup(self._purge_spawned_movements)

	def _purge_spawned_movements(self):
		# A Calving moves the dam into the milking herd as a Movement event of its own.
		for name in frappe.get_all("Livestock Event", {"animal": self.cow, "event_type": "Movement"}, pluck="name"):
			frappe.db.delete("Livestock Event", {"name": name})
		frappe.db.commit()

	def _service(self, date):
		doc = make_event("Service", self.cow, date, service_type="A.I.", service_date=date)
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.submit()
		return doc

	def _diagnose(self, service, date, result="Confirmed"):
		doc = make_event(
			"Pregnancy Diagnosis", self.cow, date,
			related_service=service.name, diagnosis_date=date, diagnosis_result=result,
		)
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.submit()
		return doc

	def _calving(self, date):
		doc = make_event(
			"Calving", self.cow, date, custom_calving_outcome="Live Birth", custom_no_of_calves=1
		)
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.submit()
		return doc

	def _cow(self):
		return frappe.db.get_value(
			"Animal", self.cow,
			["repro_status", "last_service_date", "expected_calving_date", "last_calving_date", "parity"],
			as_dict=True,
		)

	# -- the 45-day wait ---------------------------------------------------

	def test_a_backdated_service_before_a_later_calving_goes_through(self):
		s = self._service("2026-01-01")
		self._diagnose(s, "2026-02-01")
		self._calving("2026-10-01")
		earlier = self._service("2025-03-01")  # raised "Too early to serve her" before
		self.assertEqual(earlier.docstatus, 1)

	def test_a_service_ten_days_after_calving_is_still_refused(self):
		s = self._service("2026-01-01")
		self._diagnose(s, "2026-02-01")
		self._calving("2026-10-01")
		with self.assertRaises(frappe.ValidationError):
			make_event("Service", self.cow, "2026-10-11", service_type="A.I.", service_date="2026-10-11").submit()

	# -- Rule 1: an earlier Service still Pending ----------------------------

	def test_a_pending_service_dated_later_does_not_block_an_earlier_one(self):
		self._service("2026-03-01")
		self.assertEqual(self._service("2026-01-01").docstatus, 1)

	def test_a_pending_service_dated_earlier_still_blocks(self):
		self._service("2026-01-01")
		with self.assertRaises(frappe.ValidationError):
			make_event("Service", self.cow, "2026-02-01", service_type="A.I.", service_date="2026-02-01").submit()

	def test_a_pending_service_today_blocks_a_service_today(self):
		self._service(add_days(today(), -1))
		with self.assertRaises(frappe.ValidationError):
			make_event("Service", self.cow, today(), service_type="A.I.", service_date=today()).submit()

	# -- Rule 2: an open confirmed pregnancy ---------------------------------

	def test_a_service_dated_before_an_open_pregnancy_is_allowed_and_inside_it_refused(self):
		s = self._service("2026-03-01")
		self._diagnose(s, "2026-04-01")
		self.assertEqual(self._service("2025-12-01").docstatus, 1)
		with self.assertRaises(frappe.ValidationError):
			make_event("Service", self.cow, "2026-08-01", service_type="A.I.", service_date="2026-08-01").submit()

	def test_a_service_after_the_calving_that_closed_the_pregnancy_is_allowed(self):
		s = self._service("2025-01-01")
		self._diagnose(s, "2025-02-01")
		self._calving("2025-10-08")
		self.assertEqual(self._service("2025-12-01").docstatus, 1)

	def test_a_service_inside_a_pregnancy_that_a_later_calving_closed_is_refused(self):
		s = self._service("2025-01-01")
		self._diagnose(s, "2025-02-01")
		self._calving("2025-10-08")
		with self.assertRaises(frappe.ValidationError):
			make_event("Service", self.cow, "2025-06-01", service_type="A.I.", service_date="2025-06-01").submit()

	# -- the second Confirmed diagnosis ------------------------------------

	def test_an_older_pregnancy_can_be_confirmed_after_a_newer_one(self):
		newer = self._service("2026-03-01")
		self._diagnose(newer, "2026-04-01")
		older = self._service("2025-01-01")
		self.assertEqual(self._diagnose(older, "2025-02-01").docstatus, 1)

	def test_a_second_confirmation_with_no_calving_between_is_still_refused(self):
		a = self._service("2025-01-01")
		self._diagnose(a, "2025-02-01")
		with self.assertRaises(frappe.ValidationError):
			b = make_event("Service", self.cow, "2025-05-01", service_type="A.I.", service_date="2025-05-01")
			b.submit()
			self._diagnose(b, "2025-06-01")

	# -- the Animal shows the newest event ---------------------------------

	def test_a_backdated_service_does_not_overwrite_a_newer_pregnancy(self):
		s = self._service("2026-03-01")
		self._diagnose(s, "2026-04-01")
		before = self._cow()
		self.assertEqual(before.repro_status, "Pregnant")
		self._service("2025-01-01")
		after = self._cow()
		self.assertEqual(after.repro_status, "Pregnant")
		self.assertEqual(str(after.last_service_date), "2026-03-01")
		self.assertEqual(after.expected_calving_date, before.expected_calving_date)

	def test_cancelling_the_newest_event_puts_the_animal_back(self):
		first = self._service("2025-01-01")
		second = self._service_after_failure(first)
		self.assertEqual(self._cow().repro_status, "Served")
		self.assertEqual(str(self._cow().last_service_date), "2025-03-01")
		second.cancel()
		self.assertEqual(str(self._cow().last_service_date), "2025-01-01")

	def _service_after_failure(self, first):
		self._diagnose(first, "2025-02-01", "Not Pregnant")
		return self._service("2025-03-01")

	def test_recompute_replays_history_in_date_order(self):
		s = self._service("2026-03-01")
		self._diagnose(s, "2026-04-01")
		frappe.db.set_value("Animal", self.cow, {"repro_status": "Open", "last_service_date": None, "expected_calving_date": None})
		recompute_repro_state(self.cow)
		got = self._cow()
		self.assertEqual(got.repro_status, "Pregnant")
		self.assertEqual(str(got.last_service_date), "2026-03-01")
		self.assertIsNotNone(got.expected_calving_date)

	# -- a calving for a calf that is already on the register ----------------

	def test_a_calving_can_link_a_calf_that_already_exists_without_creating_one(self):
		s = self._service("2026-01-01")
		self._diagnose(s, "2026-02-01")
		calf = frappe.get_doc({
			"doctype": "Animal", "tag_number": "TEST-ASOF-CALF", "burn_name": "TEST-ASOF-CALF",
			"sex": "Female", "status": "Active", "dam": self.cow, "date_of_birth": "2026-10-05",
		}).insert()
		self.addCleanup(_delete_and_commit, "Animal", calf.name)
		animals = frappe.db.count("Animal")
		parity = self._cow().parity or 0

		calving = self._calving("2026-10-05")
		birth = make_event(
			"Birth", calf.name, "2026-10-05", dam=self.cow, related_calving=calving.name,
			calf_sex="Female", calf_tag_number=calf.name,
		)
		self.addCleanup(_delete_and_commit, "Livestock Event", birth.name)
		birth.submit()

		self.assertEqual(frappe.db.count("Animal"), animals)
		self.assertEqual(birth.animal, calf.name)
		self.assertEqual(frappe.db.get_value("Livestock Event", calving.name, "births_recorded"), 1)
		cow = self._cow()
		self.assertEqual(cow.repro_status, "Open")
		self.assertEqual(str(cow.last_calving_date), "2026-10-05")
		self.assertEqual(cow.parity, parity + 1)
		self.assertEqual(frappe.db.get_value("Livestock Event", s.name, "pregnancy_confirmation_status"), "Confirmed")
