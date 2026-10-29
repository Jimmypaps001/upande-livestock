# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Natural service is recorded when it is perceived: from a diagnosis or from a calving."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.breeding.create_pregnancy_diagnosis import create_pregnancy_diagnosis
from upande_livestock.serverscripts.breeding.create_service_event import create_service_event
from upande_livestock.serverscripts.breeding.record_birth import record_birth
from upande_livestock.serverscripts.breeding.sire_candidates import sire_candidates
from upande_livestock.serverscripts.tests.beef_fixtures import (
	isolate, make_animal, make_herd, test_employee,
)


def ago(days):
	return add_days(today(), -days)


class TestNaturalPdAndCalving(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.op = test_employee()
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 0)
		self.group = make_herd("ZZ NP Lactation", "Breeding").name
		self.cow = make_animal(self.group, sex="Female", date_of_birth=ago(3000))
		self.bull = make_animal(self.group, sex="Male", date_of_birth=ago(2500))

	def _pd(self, **extra):
		return create_pregnancy_diagnosis({
			"animal": self.cow.name, "diagnosis_result": "Confirmed", "operator": self.op, **extra})

	def test_pd_with_a_conception_date_and_no_service_makes_a_backdated_natural_service(self):
		got = self._pd(conception_date=ago(100))
		self.assertTrue(got.get("ok"), got)
		self.assertTrue(got["service_created"])
		svc = frappe.get_doc("Livestock Event", got["service"])
		self.assertEqual((svc.service_type, svc.custom_is_backdated, str(svc.conception_date)),
		                 ("Natural", 1, ago(100)))
		self.assertEqual(str(svc.service_date), ago(100))
		# the system derived it, so the closed window did not refuse it; the diagnosis links to it
		self.assertEqual(frappe.db.get_value("Livestock Event", got["name"], "related_service"), svc.name)
		self.assertEqual(svc.pregnancy_confirmation_status, "Confirmed")
		# and the only bull in her herd was named, inferred
		self.assertEqual((got["sire_animal"], got["sire_inferred"]), (self.bull.name, True))
		self.assertIn("was in ZZ NP Lactation", got["sire_basis"])

	def test_foetal_age_in_weeks_gives_the_conception_date(self):
		got = self._pd(foetal_age_weeks=14)
		self.assertTrue(got.get("ok"), got)
		svc = frappe.get_doc("Livestock Event", got["service"])
		self.assertEqual(str(svc.conception_date), add_days(today(), -98))

	def test_user_picked_sire_wins_over_inference(self):
		other = make_animal(self.group, sex="Male", date_of_birth=ago(2500))
		got = self._pd(conception_date=ago(100), sire_animal=self.bull.name)
		self.assertEqual((got["sire_animal"], got["sire_inferred"]), (self.bull.name, False))
		self.assertTrue(other)

	def test_two_bulls_leave_the_sire_blank_with_candidates(self):
		other = make_animal(self.group, sex="Male", date_of_birth=ago(2500))
		got = self._pd(conception_date=ago(100))
		self.assertEqual(got["sire_animal"], "")
		self.assertEqual(sorted(c["animal"] for c in got["candidates"]), sorted([self.bull.name, other.name]))
		pre = sire_candidates(self.cow.name, ago(100))
		self.assertEqual((pre["sire_animal"], pre["inferred"]), (None, False))
		self.assertEqual(len(pre["candidates"]), 2)

	def test_sire_unknown_is_respected(self):
		got = self._pd(conception_date=ago(100), sire_unknown=1)
		self.assertEqual((got["sire_animal"], got["sire_inferred"]), ("", False))

	def test_preview_names_one_bull(self):
		pre = sire_candidates(self.cow.name, ago(100))
		self.assertEqual((pre["sire_animal"], pre["inferred"], pre["label"]),
		                 (self.bull.name, True, self.bull.name))

	def test_service_type_defaults_from_settings(self):
		got = create_service_event({"animal": self.cow.name, "operator": self.op})
		self.assertTrue(got.get("ok"), got)
		self.assertEqual(got["service_type"], "Natural")
		self.assertEqual((got["sire_animal"], got["sire_inferred"]), (self.bull.name, True))
		self.assertEqual(got["conception_date"], today())

	def test_a_service_by_a_relative_warns(self):
		frappe.db.set_value("Animal", self.cow.name, "sire", self.bull.name)
		got = create_service_event({"animal": self.cow.name, "operator": self.op, "service_type": "Natural"})
		self.assertTrue(got.get("ok"), got)
		self.assertIn("sire of", got["warnings"][0])
		self.assertEqual(frappe.db.get_value("Livestock Event", got["name"], "kinship_warnings"), got["warnings"][0])

	def test_ai_is_unaffected_by_inference(self):
		got = create_service_event({"animal": self.cow.name, "operator": self.op,
		                            "service_type": "A.I.", "sire": "Mazira"})
		self.assertTrue(got.get("ok"), got)
		self.assertEqual((got["service_type"], got["sire_animal"], got["sire_inferred"]), ("A.I.", "", False))
		self.assertEqual(frappe.db.get_value("Livestock Event", got["name"], "sire"), "Mazira")

	def test_calving_with_no_service_derives_one_and_stamps_the_calf_sire(self):
		got = record_birth({
			"dam": self.cow.name, "operator": self.op, "outcome": "Live Birth",
			"calves": [{"sex": "Male", "birth_weight": 32}]})
		self.assertTrue(got.get("ok"), got)
		self.assertTrue(got["service_created"])
		svc = frappe.get_doc("Livestock Event", got["service"])
		self.assertEqual(str(svc.conception_date), add_days(today(), -280))
		self.assertEqual(svc.pregnancy_confirmation_status, "Confirmed")
		calf = frappe.db.get_value("Animal", got["calves"][0]["animal"] if "animal" in got["calves"][0]
		                           else got["calves"][0]["name"],
		                           ["sire", "sire_name", "dam", "current_herd"], as_dict=True)
		self.assertEqual((calf.sire, calf.sire_name, calf.dam), (self.bull.name, self.bull.name, self.cow.name))
		# the calf lives in its mother's herd
		self.assertEqual(calf.current_herd, self.group)

	def test_the_dairy_default_still_refuses_a_calving_with_no_service(self):
		frappe.db.set_single_value("Livestock Settings", "default_service_type", "A.I.")
		got = record_birth({
			"dam": self.cow.name, "operator": self.op, "outcome": "Live Birth",
			"calves": [{"sex": "Male", "birth_weight": 32}]})
		self.assertIn("No active pregnancy", got["error"])

	def test_pd_without_a_date_or_service_is_refused(self):
		got = self._pd()
		self.assertIn("no service awaiting", got["error"])
