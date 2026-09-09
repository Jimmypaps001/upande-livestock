# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.serverscripts.common.guards import check_guards


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


class TestBackdatedGuards(IntegrationTestCase):
	"""Deworming carries a minimum-interval rule. Two of them close together
	must be refused for a live entry and allowed for a historical one."""

	def setUp(self):
		_set_window(0)
		tag = frappe.generate_hash(length=10)
		self.animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": tag,
				"burn_name": tag,
				"sex": "Female",
				"status": "Active",
				"date_of_birth": add_months(today(), -36),
			}
		).insert(ignore_permissions=True)
		self.operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")

	def tearDown(self):
		_set_window(0)
		frappe.db.rollback()

	def _event(self, event_date, backdated=0):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Deworming",
				"event_date": event_date,
				"operator": self.operator,
				"custom_is_backdated": backdated,
			}
		)
		return doc

	def _anchor(self, event_date):
		doc = self._event(event_date)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_a_live_event_too_soon_is_still_refused(self):
		"""The exemption must not leak into today's entries — that is the whole
		reason it keys on the flag rather than on the window alone."""
		self._anchor(add_days(today(), -2))
		with self.assertRaises(frappe.ValidationError):
			check_guards(self._event(today()))

	def test_a_backdated_event_too_soon_passes_while_the_window_is_open(self):
		_set_window(1)
		self._anchor(add_days(today(), -100))
		check_guards(self._event(add_days(today(), -98), backdated=1))  # must not throw

	def test_a_backdated_event_is_still_guarded_when_the_window_is_closed(self):
		_set_window(0)
		self._anchor(add_days(today(), -100))
		with self.assertRaises(frappe.ValidationError):
			check_guards(self._event(add_days(today(), -98), backdated=1))

	def test_a_live_event_is_unaffected_by_an_open_window(self):
		_set_window(1)
		self._anchor(add_days(today(), -2))
		with self.assertRaises(frappe.ValidationError):
			check_guards(self._event(today()))
