# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What a client can leave out when recording a milking.

`milking_time` is mandatory on the doctype and has no default, because a
milking is identified by when it happened — see
`patches.migrate_milking_session_to_time`, which replaced the old AM/PM
`session` Select with it. A client that inserts the document directly gets
"Value missing for Milk Recording: Milking Time" and nothing is recorded.

`create_milk_recording` fills it from the server clock instead, so a handset
that has a herd and a weight can record a milking without the operator having
to key a time. That default is the reason the mobile milk form works at all;
these pin it, and pin that a supplied time still wins.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.milking.create_milk_recording import create_milk_recording


def _purge(marker):
	for name in frappe.get_all("Milk Recording", filters={"remarks": ["like", f"%{marker}%"]}, pluck="name"):
		doc = frappe.get_doc("Milk Recording", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Milk Recording", name, force=True, ignore_permissions=True)
	frappe.db.commit()


class TestMilkRecordingTime(IntegrationTestCase):
	MARKER = "TEST-MILKTIME"

	def setUp(self):
		self.herd = frappe.db.get_value("Herds", {"custom_is_milking": 1}, "name")
		if not self.herd:
			self.skipTest("no milking herd on this site")
		_purge(self.MARKER)
		self.addCleanup(_purge, self.MARKER)

	def _record(self, **extra):
		return create_milk_recording({
			"herd": self.herd,
			"recording_date": "2026-09-03",
			"total_yield_kg": 10.0,
			"remarks": self.MARKER,
			**extra,
		})

	def test_a_milking_records_without_a_time(self):
		"""The handset sends a herd and a weight; the server knows the clock."""
		result = self._record()
		self.assertTrue(result.get("ok"), result.get("error"))
		self.assertTrue(
			frappe.db.get_value("Milk Recording", result["name"], "milking_time"),
			"milking_time was left empty, so the doctype's reqd check will reject it",
		)

	def test_a_time_without_seconds_is_accepted(self):
		"""The handset's picker emits HH:MM, not HH:MM:SS.

		Frappe parses both, but the app sends the short form, so a change that
		started requiring seconds would break the milk form and nothing else
		would notice.
		"""
		result = self._record(milking_time="05:30")
		self.assertTrue(result.get("ok"), result.get("error"))
		self.assertEqual(
			str(frappe.db.get_value("Milk Recording", result["name"], "milking_time")),
			"5:30:00",
		)

	def test_a_supplied_time_is_kept(self):
		"""A 05:30 milking entered at 14:00 must not be stamped 14:00."""
		result = self._record(milking_time="05:30:00")
		self.assertTrue(result.get("ok"), result.get("error"))
		self.assertEqual(
			str(frappe.db.get_value("Milk Recording", result["name"], "milking_time")),
			"5:30:00",
		)

	def test_the_field_the_app_used_to_send_is_gone(self):
		"""`session` was replaced by `milking_time`.

		The mobile app kept sending `session` and never sent `milking_time`, so
		every milking it tried to record failed on the mandatory check. This
		fails if the field ever comes back, which would make that payload look
		valid again.
		"""
		self.assertIsNone(
			frappe.get_meta("Milk Recording").get_field("session"),
			"`session` is back on Milk Recording; the app's old payload is ambiguous again",
		)
