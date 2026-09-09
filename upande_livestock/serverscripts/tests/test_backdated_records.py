# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The five non-event writes stamp custom_is_backdated too.

Every event-shaped write (new_livestock_event) already stamps and is covered by
test_backdated_events.py. These five — weight, milk recording, health case,
check-up and disposal — build their own document directly rather than going
through new_livestock_event, so each needed the same three lines added by hand:
resolve, assert_allowed, stamp. This file only exercises weight and milk
recording directly (the other three share the identical shape and are exercised
for the guard/refusal behaviour in test_operations.py); it is here to catch a
mis-wired stamp, not to re-prove the whole endpoint.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.serverscripts.weights.create_weight_record import create_weight_record
from upande_livestock.serverscripts.milking.create_milk_recording import create_milk_recording


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


class TestBackdatedRecords(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(_set_window, 0)
		_set_window(1)
		tag = frappe.generate_hash(length=10)
		self.animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": tag,
				"burn_name": tag,
				"sex": "Female",
				"status": "Active",
				"date_of_birth": add_months(today(), -30),
			}
		).insert(ignore_permissions=True)
		self.operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")

	def test_a_backdated_weight_is_stamped(self):
		past = add_days(today(), -20)
		res = create_weight_record(
			{
				"animal": self.animal.name,
				"weight_date": past,
				"weight_kg": 410,
				"operator": self.operator,
			}
		)
		self.assertNotIn("error", res, res.get("error"))
		doc = frappe.get_doc("Livestock Weight Record", res["name"])
		self.assertEqual(doc.custom_is_backdated, 1)
		self.assertEqual(str(doc.weight_date), past)

	def test_a_live_weight_is_not_stamped(self):
		res = create_weight_record(
			{
				"animal": self.animal.name,
				"weight_date": today(),
				"weight_kg": 410,
				"operator": self.operator,
			}
		)
		self.assertNotIn("error", res, res.get("error"))
		doc = frappe.get_doc("Livestock Weight Record", res["name"])
		self.assertEqual(doc.custom_is_backdated, 0)

	def test_a_backdated_milk_recording_is_stamped(self):
		herd = frappe.db.get_value("Herds", {}, "name")
		if not herd:
			self.skipTest("no Herds row on this site")
		past = add_days(today(), -7)
		res = create_milk_recording(
			{
				"herd": herd,
				"recording_date": past,
				"milking_time": "06:00:00",
				"total_yield_kg": 120,
				"operator": self.operator,
			}
		)
		self.assertNotIn("error", res, res.get("error"))
		doc = frappe.get_doc("Milk Recording", res["name"])
		self.assertEqual(doc.custom_is_backdated, 1)

	def test_a_backdated_record_is_refused_when_the_window_is_closed(self):
		_set_window(0)
		res = create_weight_record(
			{
				"animal": self.animal.name,
				"weight_date": add_days(today(), -20),
				"weight_kg": 410,
				"operator": self.operator,
			}
		)
		self.assertIn("error", res)
		self.assertIn("Backdating is closed", res["error"])
