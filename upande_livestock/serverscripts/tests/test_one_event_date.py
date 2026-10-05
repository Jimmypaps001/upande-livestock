# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A Service and a Pregnancy Diagnosis have one date.

`service_date` and `diagnosis_date` were separate fields beside `event_date`,
both on the form, and nothing kept them in step.
"""

import unittest

import frappe


class TestOneDate(unittest.TestCase):
	def _event(self, event_type, **values):
		doc = frappe.new_doc("Livestock Event")
		doc.update({"event_type": event_type, **values})
		doc.one_date()
		return doc

	def test_the_service_date_follows_the_event_date(self):
		doc = self._event("Service", event_date="2026-09-01", service_date="2026-08-20")
		self.assertEqual(str(doc.service_date), "2026-09-01")

	def test_a_caller_sending_only_the_service_date_has_it_taken_as_the_date(self):
		doc = self._event("Service", event_date=None, service_date="2026-08-20")
		self.assertEqual((str(doc.event_date), str(doc.service_date)), ("2026-08-20", "2026-08-20"))

	def test_a_diagnosis_date_follows_the_event_date(self):
		doc = self._event("Pregnancy Diagnosis", event_date="2026-09-03", diagnosis_date="2026-09-01")
		self.assertEqual(str(doc.diagnosis_date), "2026-09-03")

	def test_other_events_are_left_alone(self):
		doc = self._event("Movement", event_date="2026-09-03", service_date=None)
		self.assertIsNone(doc.service_date)
