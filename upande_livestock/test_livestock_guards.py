# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.livestock_guards import AGE_RULES, INTERVAL_RULES, animal_age_months

SETTINGS_KEYS = (
	"min_service_age_months",
	"min_calving_age_months",
	"min_calving_interval_days",
	"min_vaccination_interval_days",
	"min_deworming_interval_days",
	"min_weight_recording_interval_days",
	"min_hoof_trimming_interval_days",
)


def _delete_and_commit(doctype, name):
	"""Hard-delete and commit.

	IntegrationTestCase gives this class a single rollback at the end of the
	whole class, not one per test, and ensure_livestock_event_types() (called
	from setUp) itself commits — so nothing inserted after that commit is ever
	rolled back automatically. Every Animal and Livestock Event these tests
	create must therefore be cleaned up (and that cleanup committed)
	explicitly, matching the pattern already established in
	test_livestock_event.py, or it is left behind in the live database
	forever, inflating tabAnimal / tabLivestock Event past their documented
	invariant counts.
	"""
	frappe.db.delete(doctype, {"name": name})
	frappe.db.commit()


class TestLivestockGuards(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		for key in SETTINGS_KEYS:
			frappe.db.set_single_value("Livestock Settings", key, None)
		frappe.clear_cache()
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def tearDown(self):
		for key in SETTINGS_KEYS:
			frappe.db.set_single_value("Livestock Settings", key, None)
		frappe.clear_cache()

	def _animal(self, tag, age_months):
		# Defensive, not just idempotent: a stray row from an earlier
		# interrupted run must be purged (Events first, since Animal cannot be
		# deleted while a Livestock Event still links to it) before creating a
		# fresh fixture under the same tag.
		frappe.db.delete("Livestock Event", {"animal": tag})
		frappe.db.delete("Animal", {"name": tag})
		frappe.db.commit()
		animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": tag,
				"burn_name": tag,
				"sex": "Female",
				"status": "Active",
				"date_of_birth": add_months(today(), -age_months),
			}
		).insert()
		# Registered immediately after insert() returns, before the caller
		# makes any assertions, so a failing assertion still leaves the row
		# scheduled for deletion.
		self.addCleanup(_delete_and_commit, "Animal", animal.name)
		return animal

	def _event(self, event_type, animal, event_date, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": animal,
				"event_type": event_type,
				"event_date": event_date,
				"operator": self.operator,
				**kwargs,
			}
		)
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		return doc

	def test_rule_tables_cover_the_documented_defaults(self):
		self.assertEqual(AGE_RULES["Service"]["default"], 15)
		self.assertEqual(AGE_RULES["Calving"]["default"], 24)
		self.assertEqual(INTERVAL_RULES["Calving"]["default"], 270)
		self.assertEqual(INTERVAL_RULES["Vaccination"]["default"], 21)
		self.assertEqual(INTERVAL_RULES["Deworming"]["default"], 90)
		self.assertEqual(INTERVAL_RULES["Hoof Trimming"]["default"], 90)
		self.assertEqual(INTERVAL_RULES["Weight Recording"]["default"], 7)

	def test_animal_age_months_is_computed_from_date_of_birth(self):
		animal = self._animal("TEST-GUARD-AGE", 30)
		self.assertAlmostEqual(animal_age_months(animal.name, today()), 30, delta=1)

	def test_animal_with_no_dob_is_not_age_blocked(self):
		tag = "TEST-GUARD-NODOB"
		frappe.db.delete("Livestock Event", {"animal": tag})
		frappe.db.delete("Animal", {"name": tag})
		frappe.db.commit()
		animal = frappe.get_doc(
			{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
		).insert()
		self.addCleanup(_delete_and_commit, "Animal", animal.name)
		self.assertIsNone(animal_age_months(animal.name, today()))
		doc = self._event("Service", animal.name, today(), service_date=today())
		self.assertTrue(doc.name)

	def test_service_below_minimum_age_is_blocked(self):
		animal = self._animal("TEST-GUARD-YOUNG", 10)
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._event("Service", animal.name, today(), service_date=today())

	def test_service_at_or_above_minimum_age_passes(self):
		animal = self._animal("TEST-GUARD-OLD", 20)
		doc = self._event("Service", animal.name, today(), service_date=today())
		self.assertTrue(doc.name)

	def test_configured_minimum_age_is_honoured(self):
		animal = self._animal("TEST-GUARD-OLD", 20)
		frappe.db.set_single_value("Livestock Settings", "min_service_age_months", 24)
		frappe.clear_cache()
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._event("Service", animal.name, today(), service_date=today())

	def test_vaccination_inside_the_interval_is_blocked(self):
		animal = self._animal("TEST-GUARD-VAX", 30)
		first = self._event("Vaccination", animal.name, add_days(today(), -5))
		first.submit()
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._event("Vaccination", animal.name, today())

	def test_vaccination_outside_the_interval_passes(self):
		animal = self._animal("TEST-GUARD-VAX2", 30)
		first = self._event("Vaccination", animal.name, add_days(today(), -40))
		first.submit()
		doc = self._event("Vaccination", animal.name, today())
		self.assertTrue(doc.name)

	def test_draft_events_do_not_trigger_the_interval_rule(self):
		animal = self._animal("TEST-GUARD-DRAFT", 30)
		self._event("Vaccination", animal.name, add_days(today(), -5))  # left in draft
		doc = self._event("Vaccination", animal.name, today())
		self.assertTrue(doc.name)

	def test_zero_setting_disables_an_interval_rule(self):
		animal = self._animal("TEST-GUARD-ZERO", 30)
		frappe.db.set_single_value("Livestock Settings", "min_vaccination_interval_days", 0)
		frappe.clear_cache()
		first = self._event("Vaccination", animal.name, add_days(today(), -1))
		first.submit()
		doc = self._event("Vaccination", animal.name, today())
		self.assertTrue(doc.name)

	def test_untyped_event_is_not_guarded(self):
		animal = self._animal("TEST-GUARD-FEED", 3)
		doc = self._event("Feeding", animal.name, today())
		self.assertTrue(doc.name)
