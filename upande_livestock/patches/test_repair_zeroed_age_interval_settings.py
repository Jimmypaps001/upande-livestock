# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common.timings import TIMING_DEFAULTS
from upande_livestock.serverscripts.tests.timings_utils import ResetsLivestockTimings
from upande_livestock.patches.repair_zeroed_age_interval_settings import FIELDS, execute


def _raw(fieldname):
	"""The literal tabSingles value for a Livestock Settings field, or None.

	Not frappe.db.get_value("Singles", ...): Singles is a pseudo-doctype with
	no `creation`/`name` columns of its own, so the ORM's default ordering
	breaks against it. Raw SQL, matching livestock_timings.read_setting.
	"""
	rows = frappe.db.sql(
		"select `value` from `tabSingles` where doctype='Livestock Settings' and field=%s",
		(fieldname,),
	)
	return rows[0][0] if rows else None


def _set_raw(fieldname, value):
	"""Write tabSingles directly, bypassing LivestockSettings.validate().

	The bug this patch repairs was never possible through the desk UI once
	Livestock Settings' zero-rejection validation covered these fields — it is
	a leftover from before that, so reproducing it for a test has to go
	around validate() the same way the original bug did (a None -> 0 cint()
	coercion at db_update() time, not a hand-typed 0 that validate() would
	catch). Delete-then-insert rather than update, so it works whether or not
	a row already exists.
	"""
	frappe.db.sql("delete from `tabSingles` where doctype='Livestock Settings' and field=%s", (fieldname,))
	frappe.db.sql(
		"insert into `tabSingles` (doctype, field, value) values ('Livestock Settings', %s, %s)",
		(fieldname, value),
	)
	frappe.db.commit()


class TestRepairZeroedAgeIntervalSettings(ResetsLivestockTimings, IntegrationTestCase):
	"""Drive the patch against fields deliberately left zeroed.

	Asserting "every one of the seven fields holds its real default" would be
	hollow once the live repair has run for real — it would stay true forever
	after, passing against a stubbed execute(). Each test below writes its own
	'0' (or leaves its own non-'0' value) immediately before calling execute(),
	so a stub — or a version of the patch that touches the wrong fields — fails.
	"""

	def test_repairs_a_field_stored_as_literal_zero(self):
		_set_raw("min_service_age_months", "0")
		repaired = execute()
		self.assertEqual(_raw("min_service_age_months"), "15")
		self.assertIn(("min_service_age_months", 15), repaired)

	def test_repairs_all_seven_fields_in_one_call(self):
		for fieldname in FIELDS:
			_set_raw(fieldname, "0")

		repaired = execute()

		self.assertEqual({name for name, _ in repaired}, set(FIELDS))
		for fieldname in FIELDS:
			self.assertEqual(_raw(fieldname), str(TIMING_DEFAULTS[fieldname]))

	def test_a_real_nonzero_value_is_left_alone(self):
		_set_raw("min_calving_interval_days", "300")
		repaired = execute()
		self.assertNotIn("min_calving_interval_days", {name for name, _ in repaired})
		self.assertEqual(_raw("min_calving_interval_days"), "300")

	def test_an_unset_field_is_left_alone(self):
		frappe.db.sql(
			"delete from `tabSingles` where doctype='Livestock Settings' and field=%s",
			("min_deworming_interval_days",),
		)
		frappe.db.commit()
		repaired = execute()
		self.assertNotIn("min_deworming_interval_days", {name for name, _ in repaired})
		self.assertIsNone(_raw("min_deworming_interval_days"))

	def test_a_breeding_timing_zeroed_deliberately_is_not_touched(self):
		"""post_abortion_min_service_days = 0 is a real, valid configuration.

		This patch's FIELDS list must never include the two
		ZERO_MEANS_DISABLED breeding timings — this test fails loudly if a
		future edit widens FIELDS to include one of them.
		"""
		_set_raw("post_abortion_min_service_days", "0")
		repaired = execute()
		self.assertNotIn("post_abortion_min_service_days", {name for name, _ in repaired})
		self.assertEqual(_raw("post_abortion_min_service_days"), "0")

	def test_patch_is_idempotent(self):
		_set_raw("min_hoof_trimming_interval_days", "0")
		execute()
		once = _raw("min_hoof_trimming_interval_days")
		repaired_again = execute()
		self.assertNotIn("min_hoof_trimming_interval_days", {name for name, _ in repaired_again})
		self.assertEqual(_raw("min_hoof_trimming_interval_days"), once)
