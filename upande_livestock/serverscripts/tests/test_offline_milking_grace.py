# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A milking recorded offline may sync one day late with backdating closed.

The check is the milking's date against server today. captured_at is audit.
Direct online submissions get no grace."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import herd_movement
from upande_livestock.serverscripts.mobile.record_milking import record_milking
from upande_livestock.serverscripts.tests.test_milking import _purge

MARKER = "TEST-OFFLINEGRACE"


class TestOfflineMilkingGrace(IntegrationTestCase):
	def setUp(self):
		self.herd = (herd_movement.milking_herds() or [None])[0]
		self.company = frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		if not (self.herd and self.company):
			self.skipTest("this site has no milking herd or company")
		self.was_open = frappe.db.get_single_value("Livestock Settings", "custom_backdating_open")
		self.was_grace = frappe.db.get_single_value("Livestock Settings", "allow_offline_milking_grace")
		self._grace(1)
		_purge(MARKER)
		self.addCleanup(self._restore)

	def _restore(self):
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", self.was_open)
		frappe.db.set_single_value("Livestock Settings", "allow_offline_milking_grace", self.was_grace)
		_purge(MARKER)

	def _grace(self, value):
		frappe.db.set_single_value("Livestock Settings", "allow_offline_milking_grace", value)

	def _window(self, value):
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)

	def _go(self, days_ago, **extra):
		return record_milking({
			"herd": self.herd,
			"recording_date": add_days(today(), -days_ago),
			"total_yield_kg": 10.0,
			"remarks": MARKER,
			**extra,
		})

	def test_offline_yesterday_is_accepted_and_stamped(self):
		self._window(0)
		got = self._go(1, offline=1, captured_at="2000-01-01 05:30:00")
		self.assertTrue(got.get("ok"), got.get("error"))
		doc = frappe.get_doc("Milk Recording", got["name"])
		self.assertEqual(doc.captured_offline, 1)
		self.assertEqual(str(doc.captured_at), "2000-01-01 05:30:00")
		self.assertEqual(str(doc.recording_date), add_days(today(), -1))

	def test_grace_used_stores_who_posted_it(self):
		self._window(0)
		got = self._go(1, offline=1)
		doc = frappe.get_doc("Milk Recording", got["name"])
		self.assertEqual(doc.late_sync_grace, 1)
		self.assertEqual(doc.posted_by_user, frappe.session.user)
		self.assertEqual(doc.posted_by_employee, frappe.db.get_value("Employee", {"user_id": frappe.session.user}))
		# Stock behaviour is unchanged: still a backdated record.
		self.assertTrue(doc.custom_is_backdated)

	def test_grace_off_refuses_yesterday_offline(self):
		self._window(0)
		self._grace(0)
		got = self._go(1, offline=1)
		self.assertIn("late offline syncs are switched off", got.get("error", ""))
		self.assertIn("ask the Livestock Manager", got["error"])
		self.assertFalse(frappe.db.exists("Milk Recording", {"remarks": MARKER}))

	def test_grace_off_but_window_open_accepts_without_the_flag(self):
		self._window(1)
		self._grace(0)
		got = self._go(1, offline=1)
		self.assertTrue(got.get("ok"), got.get("error"))
		doc = frappe.get_doc("Milk Recording", got["name"])
		self.assertFalse(doc.late_sync_grace)

	def test_todays_offline_milking_is_not_a_late_sync(self):
		self._window(0)
		doc = frappe.get_doc("Milk Recording", self._go(0, offline=1)["name"])
		self.assertFalse(doc.late_sync_grace)
		self.assertFalse(doc.posted_by_user)

	def test_only_managers_write_the_setting(self):
		roles = {p.role for p in frappe.get_meta("Livestock Settings").permissions if p.write}
		self.assertEqual(roles, {"System Manager", "Livestock Manager"})

	def test_offline_two_days_ago_is_refused(self):
		self._window(0)
		got = self._go(2, offline=1)
		self.assertIn("more than a day old", got.get("error", ""))

	def test_online_yesterday_is_refused_when_closed(self):
		self._window(0)
		got = self._go(1)
		self.assertIn("Backdating is closed", got.get("error", ""))

	def test_open_window_accepts_both(self):
		self._window(1)
		for days in (1, 2):
			got = self._go(days, offline=1)
			self.assertTrue(got.get("ok"), got.get("error"))

	def test_todays_offline_milking_posts_stock_as_usual(self):
		self._window(0)
		got = self._go(0, offline=1)
		self.assertTrue(got.get("ok"), got.get("error"))
		doc = frappe.get_doc("Milk Recording", got["name"])
		self.assertEqual(doc.captured_offline, 1)
		self.assertFalse(doc.custom_is_backdated)
