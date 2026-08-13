# Copyright (c) 2026, Upande and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import ensure_livestock_timing_defaults
from upande_livestock.livestock_timings import get_timing
from upande_livestock.livestock_timings_test_utils import ResetsLivestockTimings
from upande_livestock.upande_livestock.doctype.livestock_settings.livestock_settings import (
	ZERO_IS_INVALID,
	ZERO_MEANS_DISABLED,
)

# Livestock Settings links out to Herds (default_calf_herd, added by this
# task), plus pre-existing dairy/accounting links (Warehouse, Item, Stock
# Entry Type, Company, Account). IntegrationTestCase's automatic test-record
# dependency walk tries to build test records for all of these, which pulls
# in ERPNext's BOM/Employee/Department test-import chain and fails on a
# "Parent Department: All Departments" fixture this site does not have (same
# root cause documented in livestock_event/test_livestock_event.py). None of
# the tests below touch any of these fields, so all are safe to drop from the
# walk.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Herds", "Warehouse", "Item", "Stock Entry Type", "Company", "Account"]


class TestLivestockSettings(ResetsLivestockTimings, IntegrationTestCase):
	def setUp(self):
		# super().setUp() registers the final timing reset first (see
		# ResetsLivestockTimings), so every test in this class ends with the
		# real 11 defaults restored regardless of what it configures below or
		# whether it's the last test in the class — this class has no other
		# test class running after it to repair a leftover None the way
		# TestTimingsAreEnforcedServerSide used to rely on TestLivestockTimings
		# doing.
		super().setUp()
		# Every timing field must already hold a real value before these tests
		# start touching individual ones. Without this, an untouched field is
		# still None going into doc.save(), and base_document's None -> 0 Int
		# coercion (the bug ensure_livestock_timing_defaults exists to close)
		# zeroes it as a side effect of saving a completely unrelated field —
		# which a ZERO_IS_INVALID field then trips on the *next* save in the
		# same test, for a reason that has nothing to do with what the test is
		# actually checking.
		ensure_livestock_timing_defaults()

	def tearDown(self):
		for fieldname in (*ZERO_IS_INVALID, *ZERO_MEANS_DISABLED):
			frappe.db.set_single_value("Livestock Settings", fieldname, None)

	def test_zero_is_rejected_for_fields_where_it_is_meaningless(self):
		for fieldname in ZERO_IS_INVALID:
			doc = frappe.get_single("Livestock Settings")
			doc.set(fieldname, 0)
			with self.assertRaisesRegex(frappe.exceptions.ValidationError, "cannot be 0", msg=fieldname):
				doc.save()

	def test_zero_is_accepted_for_the_two_fields_where_it_means_disabled(self):
		for fieldname in ZERO_MEANS_DISABLED:
			doc = frappe.get_single("Livestock Settings")
			doc.set(fieldname, 0)
			doc.save()  # must not raise
			self.assertEqual(get_timing(fieldname), 0)
