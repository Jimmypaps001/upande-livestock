# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.livestock_timings import TIMING_DEFAULTS, get_timing


class TestLivestockTimings(IntegrationTestCase):
	def tearDown(self):
		for key in TIMING_DEFAULTS:
			frappe.db.set_single_value("Livestock Settings", key, None)
		frappe.clear_cache()

	def test_defaults_match_the_previously_hardcoded_values(self):
		self.assertEqual(TIMING_DEFAULTS["post_calving_min_service_days"], 45)
		self.assertEqual(TIMING_DEFAULTS["post_calving_optimal_service_days"], 60)
		self.assertEqual(TIMING_DEFAULTS["post_abortion_min_service_days"], 30)
		self.assertEqual(TIMING_DEFAULTS["gestation_period_days"], 280)
		self.assertEqual(TIMING_DEFAULTS["pregnancy_check_days_after_service"], 35)
		self.assertEqual(TIMING_DEFAULTS["heat_cycle_days"], 21)
		self.assertEqual(TIMING_DEFAULTS["diagnosis_earliest_days"], 21)
		self.assertEqual(TIMING_DEFAULTS["diagnosis_latest_days"], 70)
		self.assertEqual(TIMING_DEFAULTS["gestation_short_warning_days"], 260)
		self.assertEqual(TIMING_DEFAULTS["gestation_long_warning_days"], 300)
		self.assertEqual(TIMING_DEFAULTS["calving_alert_lead_days"], 7)

	def test_unset_setting_falls_back_to_the_default(self):
		self.assertEqual(get_timing("gestation_period_days"), 280)

	def test_configured_value_wins(self):
		frappe.db.set_single_value("Livestock Settings", "gestation_period_days", 285)
		frappe.clear_cache()
		self.assertEqual(get_timing("gestation_period_days"), 285)

	def test_zero_is_honoured_and_not_treated_as_unset(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 0)
		frappe.clear_cache()
		self.assertEqual(get_timing("post_abortion_min_service_days"), 0)

	def test_unknown_key_raises(self):
		with self.assertRaises(KeyError):
			get_timing("no_such_timing")

	def test_every_default_has_a_settings_field(self):
		meta = frappe.get_meta("Livestock Settings")
		for key in TIMING_DEFAULTS:
			self.assertIsNotNone(meta.get_field(key), f"Livestock Settings is missing {key}")


def _delete_and_commit(doctype, name):
	"""Hard-delete and commit.

	ensure_livestock_event_types() commits (see Livestock Event Type's own
	tests), so IntegrationTestCase's single class-level rollback cannot undo
	anything created after that commit. Each row created below must therefore
	be cleaned up (and that cleanup committed) explicitly, or it is left
	behind in the live database forever, inflating tabLivestock Event's row
	count past 576.
	"""
	frappe.db.delete(doctype, {"name": name})
	frappe.db.commit()


class TestTimingsAreEnforcedServerSide(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		if frappe.db.exists("Animal", "TEST-TIMING-1"):
			frappe.delete_doc("Animal", "TEST-TIMING-1", force=True, ignore_permissions=True)
			frappe.db.commit()
		self.animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": "TEST-TIMING-1",
				"burn_name": "TEST-TIMING-1",
				"sex": "Female",
				"status": "Active",
			}
		).insert()
		# Registered before any event referencing this animal, so LIFO cleanup
		# deletes the events first.
		self.addCleanup(_delete_and_commit, "Animal", self.animal.name)
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def tearDown(self):
		frappe.db.set_single_value("Livestock Settings", "post_calving_min_service_days", None)
		frappe.db.set_single_value("Livestock Settings", "gestation_period_days", None)
		frappe.clear_cache()

	def _calving(self, event_date):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Calving",
				"event_date": event_date,
				"operator": self.operator,
				"custom_calving_outcome": "Live Birth",
				"custom_no_of_calves": 1,
			}
		)
		doc.flags.ignore_validate = True
		doc.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", doc.name)
		doc.submit()
		return doc

	def test_configured_post_calving_block_is_enforced(self):
		self._calving("2026-01-01")
		frappe.db.set_single_value("Livestock Settings", "post_calving_min_service_days", 90)
		frappe.clear_cache()
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Service",
				"event_date": "2026-03-02",
				"service_date": "2026-03-02",
				"operator": self.operator,
			}
		)
		# If the guard this test exercises is ever broken, insert() succeeds
		# instead of raising, which would otherwise leave the resulting row
		# behind in the live table with nothing left to clean it up by.
		self.addCleanup(
			lambda: (
				frappe.db.delete("Livestock Event", {"animal": self.animal.name, "event_type": "Service"}),
				frappe.db.commit(),
			)
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			service.insert()

	def test_configured_gestation_shifts_expected_calving_date(self):
		frappe.db.set_single_value("Livestock Settings", "gestation_period_days", 285)
		frappe.clear_cache()
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Service",
				"event_date": "2026-05-01",
				"service_date": "2026-05-01",
				"operator": self.operator,
			}
		)
		service.insert()
		self.addCleanup(_delete_and_commit, "Livestock Event", service.name)
		self.assertEqual(str(service.expected_calving_date), add_days("2026-05-01", 285))
