# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who each breeding screen may offer, and why the narrowing is not cosmetic.

An event recorded against an animal it cannot biologically have happened to does
not stay a bad row. A calving creates a calf and closes a pregnancy; a confirmed
diagnosis drives the feed forecast for months. The cheapest place to prevent all
of that is the list the screen offers.

EVERY THRESHOLD COMES FROM LIVESTOCK SETTINGS. A 60 written into the eligibility
code would be a second, disagreeing copy of the farm's own rule — which is how
api/reproduction.py once answered 8 animals ready where this package answered 2.
These tests move the settings and expect the lists to move with them.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import herd_movement as hm
from upande_livestock.serverscripts.tests.timings_utils import set_setting
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_purge,
	_purge_events_for,
)


def _employee():
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


def _tidy(animal):
	_purge_events_for(animal)
	if frappe.db.exists("Animal", animal):
		frappe.delete_doc("Animal", animal, force=True, ignore_permissions=True)
	frappe.db.commit()


def _event(animal, kind, on, **kw):
	doc = frappe.get_doc({
		"doctype": "Livestock Event",
		"animal": animal,
		"event_type": kind,
		"event_date": on,
		"operator": _employee(),
		**kw,
	}).insert(ignore_permissions=True)
	doc.submit()
	return doc


def _confirm(animal, served_on):
	"""A service that held — the state every list below keys off."""
	return _event(
		animal, "Service", served_on,
		service_date=served_on,
		pregnancy_confirmation_status="Confirmed",
	)


def _names(rows):
	return {r["animal"] for r in rows}


class TestCalvingIsForCowsInCalf(IntegrationTestCase):
	def setUp(self):
		self.herd = (hm.service_herds() or [None])[0]
		if not (self.herd and _employee()):
			self.skipTest("no servable herd or no active Employee on this site")
		self.animal = "ELIG-CALVE-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd=self.herd)
		self.addCleanup(_tidy, self.animal)

	def test_a_cow_not_in_calf_is_never_offered(self):
		self.assertNotIn(self.animal, _names(hm.calving_candidates()))

	def test_a_cow_in_calf_is_offered_ready_only_near_her_date(self):
		_confirm(self.animal, add_days(today(), -100))
		row = next(r for r in hm.calving_candidates() if r["animal"] == self.animal)
		self.assertFalse(row["ready"])

	def test_near_her_date_is_ready(self):
		_confirm(self.animal, add_days(today(), -275))
		row = next(r for r in hm.calving_candidates() if r["animal"] == self.animal)
		self.assertTrue(row["ready"])

	def test_an_overdue_cow_comes_first(self):
		"""Overdue is the one state on this list that needs somebody today."""
		late = "ELIG-CALVE-LATE"
		_tidy(late)
		_make_cow(late, herd=self.herd)
		self.addCleanup(_tidy, late)
		_confirm(late, add_days(today(), -320))
		_confirm(self.animal, add_days(today(), -100))
		rows = hm.calving_candidates()
		order = [r["animal"] for r in rows]
		self.assertLess(order.index(late), order.index(self.animal))
		self.assertLess(rows[order.index(late)]["days_to_calving"], 0)


class TestHeatIsWiderThanServiceOnPurpose(IntegrationTestCase):
	def setUp(self):
		self.animal = "ELIG-HEAT-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd=(hm.service_herds() or [None])[0])
		self.addCleanup(_tidy, self.animal)

	def test_a_cow_of_age_is_offered(self):
		self.assertIn(self.animal, _names(hm.heat_candidates()))

	def test_a_served_cow_is_still_offered_and_marked_a_repeat(self):
		"""Her coming back into heat IS the answer to that service — the farm
		finding out the insemination failed weeks before the pregnancy check
		would have said so. The old screen used the servable list, which drops
		her the moment she is served, and so lost every repeat."""
		_event(self.animal, "Service", add_days(today(), -21),
		       service_date=add_days(today(), -21),
		       pregnancy_confirmation_status="Pending")
		row = next(r for r in hm.heat_candidates() if r["animal"] == self.animal)
		self.assertTrue(row["repeat"])
		self.assertIn(self.animal, {r["animal"] for r in hm.diagnosable_animals()},
		              "a pending service is what makes this heat a repeat")

	def test_a_cow_in_calf_is_not_offered(self):
		"""A confirmed pregnancy showing standing heat is a diagnosis to
		revisit, not a heat to record against her pregnancy."""
		_confirm(self.animal, add_days(today(), -60))
		self.assertNotIn(self.animal, _names(hm.heat_candidates()))

	def test_a_calf_is_not_offered(self):
		calf = "ELIG-HEAT-CALF"
		_tidy(calf)
		_make_cow(calf, months_old=3)
		self.addCleanup(_tidy, calf)
		self.assertNotIn(calf, _names(hm.heat_candidates()))

	def test_the_age_line_is_the_farms_own(self):
		young = "ELIG-HEAT-YOUNG"
		_tidy(young)
		_make_cow(young, months_old=10)
		self.addCleanup(_tidy, young)
		self.assertNotIn(young, _names(hm.heat_candidates()))
		set_setting(self, "min_service_age_months", 6)
		self.assertIn(young, _names(hm.heat_candidates()))
