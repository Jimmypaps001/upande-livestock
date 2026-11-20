# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An animal's page shows who inseminated her, and when.

A Service keeps its bull as free text in `sire` (294 services on live; `semen_item`
is blank on all of them). The profile read only the service TYPE, so the timeline said
"A.I." and nothing else, and no field said when she was last served or by whom."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.animals.animal_profile import animal_profile
from upande_livestock.serverscripts.tests.test_operations import _employee, _make_cow, _purge, _purge_events_for

COW = "ZZ SERVED COW"


class TestInseminationOnTheProfile(IntegrationTestCase):
	def setUp(self):
		self.cow = _make_cow(COW)
		self.addCleanup(self._tidy)

	def _tidy(self):
		_purge_events_for(COW)
		_purge("Animal", COW)
		frappe.db.commit()

	def _service(self, date, sire, basis=None):
		ev = frappe.get_doc({"doctype": "Livestock Event", "event_type": "Service", "animal": COW,
		                     "event_date": date, "operator": _employee(), "service_type": "A.I.",
		                     "sire": sire, "custom_is_backdated": 1 if date < today() else 0})
		if basis:
			ev.date_basis = basis
		ev.insert(ignore_permissions=True)
		ev.submit()
		return ev

	def test_the_timeline_names_the_bull_and_the_profile_says_when_she_was_last_served(self):
		first = self._service(add_days(today(), -40), "STORMER")
		# Settled as not held, or the rule that a pending service blocks the next one applies.
		first.db_set("pregnancy_confirmation_status", "Not Pregnant", update_modified=False)
		self._service(add_days(today(), -2), "STEADY P RF")
		got = animal_profile({"animal": COW})
		self.assertFalse(got.get("error"), got)
		served = [m for m in got["milestones"] if m["kind"] == "service"]
		self.assertEqual([m["detail"] for m in served], ["A.I. · by STORMER", "A.I. · by STEADY P RF"])
		self.assertEqual(got["lastService"]["sire"], "STEADY P RF")
		self.assertEqual(got["lastService"]["on"], add_days(today(), -2))
		self.assertEqual(got["lastService"]["type"], "A.I.")

	def test_a_service_with_no_bull_says_only_how(self):
		self._service(add_days(today(), -3), "")
		got = animal_profile({"animal": COW})
		self.assertEqual(got["milestones"][-1]["detail"], "A.I.")
		self.assertIsNone(got["lastService"]["sire"])

	def test_an_estimated_date_is_marked_on_the_milestone_and_the_last_service(self):
		self._service(add_days(today(), -5), "STORMER", basis="Estimate")
		got = animal_profile({"animal": COW})
		self.assertTrue(got["milestones"][-1]["estimated"])
		self.assertTrue(got["lastService"]["estimated"])

	def test_a_cow_never_served_has_no_last_service(self):
		got = animal_profile({"animal": COW})
		self.assertIsNone(got["lastService"])
		self.assertFalse(got["bornEstimated"])
