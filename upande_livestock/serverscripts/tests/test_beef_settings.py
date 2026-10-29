# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Beef herd section of Livestock Settings: defaults, and a configured 0 honoured."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common import beef_settings
from upande_livestock.serverscripts.common.timings import get_timing
from upande_livestock.serverscripts.tests.beef_fixtures import isolate


class TestBeefSettings(IntegrationTestCase):
	def setUp(self):
		isolate(self)

	def test_defaults(self):
		self.assertEqual(get_timing("calf_separation_age_days"), 210)
		self.assertEqual(get_timing("breeding_bull_min_age_months"), 18)
		self.assertEqual(get_timing("conception_window_days"), 10)
		self.assertEqual(beef_settings.default_service_type(), "Natural")
		self.assertTrue(beef_settings.kinship_check_on())

	def test_configured_zero_is_honoured_for_separation_age_and_window(self):
		for field in ("calf_separation_age_days", "conception_window_days"):
			frappe.db.set_single_value("Livestock Settings", field, 0)
			self.assertEqual(get_timing(field), 0)

	def test_zero_bull_age_is_refused(self):
		doc = frappe.get_single("Livestock Settings")
		doc.breeding_bull_min_age_months = 0
		self.assertRaises(frappe.ValidationError, doc.validate)

	def test_kinship_can_be_switched_off(self):
		frappe.db.set_single_value("Livestock Settings", "kinship_check", 0)
		self.assertFalse(beef_settings.kinship_check_on())

	def test_service_type_follows_settings(self):
		frappe.db.set_single_value("Livestock Settings", "default_service_type", "A.I.")
		self.assertEqual(beef_settings.default_service_type(), "A.I.")
