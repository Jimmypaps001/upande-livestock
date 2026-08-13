# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days

from upande_livestock.install import ensure_livestock_event_types, ensure_livestock_timing_defaults
from upande_livestock.livestock_timings import TIMING_DEFAULTS, get_timing, read_setting


class TestLivestockTimings(IntegrationTestCase):
	def tearDown(self):
		for key in TIMING_DEFAULTS:
			frappe.db.set_single_value("Livestock Settings", key, None)

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
		self.assertEqual(get_timing("gestation_period_days"), 285)

	def test_zero_is_honoured_and_not_treated_as_unset(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 0)
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
		# Registered first, so per addCleanup's LIFO order it runs last —
		# after every other cleanup this class or a test method registers,
		# including the _delete_and_commit calls below (which commit, and
		# therefore would otherwise permanently flush the two fields this
		# class configures to whatever they were last left at — see
		# _reset_livestock_timings' docstring). This class runs last in the
		# module (alphabetically, confirmed empirically), so without this its
		# leftover state is what a shared site is left with after every test
		# run — silently re-arming the exact bug this task's hardening exists
		# to close.
		self.addCleanup(_reset_livestock_timings)
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
		# deletes the events first (and before _reset_livestock_timings above,
		# so it still runs before that final reset).
		self.addCleanup(_delete_and_commit, "Animal", self.animal.name)
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def tearDown(self):
		frappe.db.set_single_value("Livestock Settings", "post_calving_min_service_days", None)
		frappe.db.set_single_value("Livestock Settings", "gestation_period_days", None)

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


def _reset_livestock_timings():
	"""Wipe every timing field, then reseed the true defaults.

	Registered with addCleanup rather than left to a plain tearDown() body:
	cleanups run in LIFO order after tearDown(), and — unlike code appended to
	tearDown() — still run even if tearDown() itself were to raise. Both
	TestTimingsAreEnforcedServerSide and TestLivestockTimingDefaultsSeeding
	register this first in setUp() (before any wipe of their own), so per
	LIFO it always runs last in each test, after every other cleanup either
	class registers.

	TestLivestockTimingDefaultsSeeding deliberately puts these fields into
	the wiped, unseeded state this task's whole hardening exists to close;
	TestTimingsAreEnforcedServerSide's own tearDown wipes two of them and
	then, being the module's last-running class (alphabetically, confirmed
	empirically), commits that wipe permanently via its other cleanups'
	frappe.db.commit() calls. Either way, leaving the wipe uncorrected when
	the test finishes would re-arm the exact bug on a real, shared site the
	next time anyone opens Livestock Settings and clicks Save — which is
	precisely the Important issue this function fixes.

	Wipes before reseeding rather than reseeding alone:
	ensure_livestock_timing_defaults() only fills a field that has no
	configured value, so a field a test deliberately left at a real,
	non-default value (a legitimate 285, or a legitimate 0) would otherwise
	survive untouched — leaving the shared site's on-disk state visibly
	different from the documented defaults after these classes run, instead
	of reset to them.
	"""
	for key in TIMING_DEFAULTS:
		frappe.db.set_single_value("Livestock Settings", key, None)
	ensure_livestock_timing_defaults()


class TestLivestockTimingDefaultsSeeding(IntegrationTestCase):
	"""ensure_livestock_timing_defaults() and the platform bug it closes.

	Livestock Settings is a Single. A timing field with no `tabSingles` row
	loads as None; frappe.model.base_document's get_valid_dict() coerces that
	None through cint() to 0 on the very next save of the doctype — editing
	any unrelated field, for any reason. Verified directly against this site
	before this fix existed: deleting every timing row, then loading and
	saving Livestock Settings untouched, persisted gestation_period_days as
	the string '0'. Seeding closes the gap by giving every field a real row
	before anyone can ever save over it.
	"""

	def setUp(self):
		# Registered before the wipe below — see _reset_livestock_timings'
		# docstring for why that ordering, and why it must wipe-then-reseed
		# rather than only reseed.
		self.addCleanup(_reset_livestock_timings)
		for key in TIMING_DEFAULTS:
			frappe.db.set_single_value("Livestock Settings", key, None)
		frappe.db.commit()

	def test_seeds_every_field_that_has_no_row(self):
		for key in TIMING_DEFAULTS:
			self.assertIsNone(read_setting(key), f"{key} should start with no configured value")

		ensure_livestock_timing_defaults()

		for key, default in TIMING_DEFAULTS.items():
			self.assertIsNotNone(read_setting(key), f"{key} was not seeded")
			self.assertEqual(get_timing(key), default)

	def test_does_not_overwrite_a_configured_non_default_value(self):
		frappe.db.set_single_value("Livestock Settings", "gestation_period_days", 285)
		frappe.db.commit()

		ensure_livestock_timing_defaults()

		self.assertEqual(get_timing("gestation_period_days"), 285)

	def test_does_not_overwrite_a_configured_zero(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 0)
		frappe.db.commit()

		ensure_livestock_timing_defaults()

		self.assertEqual(get_timing("post_abortion_min_service_days"), 0)

	def test_saving_livestock_settings_does_not_silently_zero_the_timings(self):
		"""The regression that matters: reproduces the actual bug, not a stand-in.

		A test that only checks Livestock Settings.validate() rejects a
		hand-typed 0 would miss this entirely — validate() runs before the
		None -> 0 coercion happens (that coercion is in get_valid_dict(), at
		db_update() time), so it never sees the zero this bug produces.
		"""
		ensure_livestock_timing_defaults()

		doc = frappe.get_single("Livestock Settings")
		doc.save()  # touches no timing field

		for key, default in TIMING_DEFAULTS.items():
			self.assertEqual(get_timing(key), default, f"{key} was zeroed by an unrelated save")
