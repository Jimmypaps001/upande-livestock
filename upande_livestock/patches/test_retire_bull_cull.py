# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches import retire_bull_cull
from upande_livestock.serverscripts.tests.beef_fixtures import isolate


class TestRetireBullCull(IntegrationTestCase):
	def setUp(self):
		isolate(self)

	def _single(self, field):
		return frappe.db.get_single_value("Livestock Settings", field)

	def test_drops_the_settings_and_closes_the_open_alerts_idempotently(self):
		for field in retire_bull_cull.SETTINGS:
			frappe.db.sql(
				"insert into `tabSingles` (doctype, field, value) values ('Livestock Settings', %s, '1')",
				(field,),
			)
		frappe.db.sql(
			"insert into `tabLivestock Alert` (name, creation, modified, owner, modified_by, docstatus, "
			"alert_kind, alert_date, status) values ('ZZ-BCD-1', now(), now(), 'Administrator', "
			"'Administrator', 0, 'Bull Cull Due', curdate(), 'Open')"
		)
		for _ in range(2):
			retire_bull_cull.execute()
		for field in retire_bull_cull.SETTINGS:
			self.assertFalse(frappe.db.exists("Singles", {"doctype": "Livestock Settings", "field": field}))
		self.assertEqual(frappe.db.get_value("Livestock Alert", "ZZ-BCD-1", "status"), "Dismissed")
