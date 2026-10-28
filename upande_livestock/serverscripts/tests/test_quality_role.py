# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The lab role: it files quality and does nothing else.

Asked as a real user holding only Livestock Quality (with an Employee behind
them, so the employee gate is not what stops the refusals).
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowtime, today

from upande_livestock.serverscripts.common import herd_movement
from upande_livestock.serverscripts.common.envelope import QUALITY_ROLE, livestock_roles
from upande_livestock.serverscripts.milking.create_milk_recording import create_milk_recording
from upande_livestock.serverscripts.mobile.record_animal_event import record_animal_event
from upande_livestock.serverscripts.mobile.record_feeding import record_feeding
from upande_livestock.serverscripts.mobile.record_milking import record_milking
from upande_livestock.serverscripts.quality.quality_options import quality_options
from upande_livestock.serverscripts.quality.quality_vs_feed import quality_vs_feed
from upande_livestock.serverscripts.quality.record_milk_quality import record_milk_quality
from upande_livestock.serverscripts.settings.posting_day import posting_day
from upande_livestock.serverscripts.tests.test_employee_gate import _drop_all, _user


class TestLivestockQualityRole(IntegrationTestCase):
	def setUp(self):
		self.herd = (herd_movement.milking_herds() or [None])[0] or frappe.db.get_value("Herds", {}, "name")
		self.operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not (self.herd and self.operator):
			raise unittest.SkipTest("no herd or employee on this site")
		frappe.set_user("Administrator")
		res = create_milk_recording({
			"herd": self.herd, "recording_date": today(), "milking_time": nowtime(),
			"cows_milked": 10, "total_yield_kg": 100, "price_per_kg": 50, "operator": self.operator,
		})
		if res.get("error"):
			raise unittest.SkipTest("could not record a milking: {}".format(res["error"][:140]))
		self.recording = res["name"]
		self.email = _user(QUALITY_ROLE)
		frappe.db.commit()
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.set_user("Administrator")
		doc = frappe.get_doc("Milk Recording", self.recording)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Milk Recording", self.recording, force=True, ignore_permissions=True)
		_drop_all()

	def test_the_role_ships_with_the_app(self):
		self.assertTrue(frappe.db.exists("Role", QUALITY_ROLE))

	def test_a_quality_user_records_quality(self):
		frappe.set_user(self.email)
		self.assertTrue(quality_options({}).get("ok"))
		self.assertTrue(quality_vs_feed({}).get("ok"))
		out = record_milk_quality({"recording": self.recording, "bulk_scc": 150, "fat_percent": 3.9})
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(out["bulk_scc"], 150)

	def test_the_phone_is_told_the_role(self):
		frappe.set_user(self.email)
		out = posting_day()
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(out["roles"], [QUALITY_ROLE])
		self.assertTrue(out["is_employee"])

	def test_it_may_not_record_anything_else(self):
		frappe.set_user(self.email)
		for out in (
			record_milking({"herd": self.herd, "total_yield_kg": 1}),
			record_animal_event({"type": "Heat Detection", "animal": "x", "event_date": today()}),
			record_feeding({"action": "manufacture", "herd": self.herd}),
		):
			self.assertTrue(out.get("error"), out)
			self.assertNotEqual(out.get("code"), "not_employee", out)
		for doctype in ("Milk Recording", "Livestock Event"):
			self.assertFalse(frappe.has_permission(doctype, "create"), doctype)
		for doctype in ("Animal", "Livestock Event", "Herds"):
			self.assertFalse(frappe.has_permission(doctype, "read"), doctype)

	def test_without_an_employee_it_is_view_only(self):
		frappe.set_user("Administrator")
		other = _user(QUALITY_ROLE, with_employee=False)
		frappe.db.commit()
		frappe.set_user(other)
		out = record_milk_quality({"recording": self.recording, "bulk_scc": 1})
		self.assertEqual(out.get("code"), "not_employee", out)
		self.assertTrue(quality_options({}).get("ok"))

	def test_livestock_roles_lists_only_the_apps_roles(self):
		self.assertEqual(livestock_roles(self.email), [QUALITY_ROLE])
