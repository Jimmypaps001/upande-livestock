# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import SEED_EVENT_TYPES, ensure_livestock_event_types


class TestLivestockEventType(IntegrationTestCase):
	def test_seeds_all_fifteen_types(self):
		ensure_livestock_event_types()
		self.assertEqual(len(SEED_EVENT_TYPES), 17)
		for seed in SEED_EVENT_TYPES:
			self.assertTrue(frappe.db.exists("Livestock Event Type", seed["name"]), seed["name"])

	def test_name_is_the_type_name(self):
		ensure_livestock_event_types()
		doc = frappe.get_doc("Livestock Event Type", "Feeding")
		self.assertEqual(doc.name, "Feeding")
		self.assertTrue(doc.is_active)

	def test_birth_creates_animal(self):
		ensure_livestock_event_types()
		self.assertTrue(frappe.db.get_value("Livestock Event Type", "Birth", "creates_animal"))
		self.assertFalse(frappe.db.get_value("Livestock Event Type", "Abortion", "creates_animal"))
		self.assertFalse(frappe.db.get_value("Livestock Event Type", "Calving", "creates_animal"))

	def test_detail_doctype_wired_for_health_types(self):
		ensure_livestock_event_types()
		self.assertEqual(
			frappe.db.get_value("Livestock Event Type", "Check Up", "detail_doctype"),
			"Livestock Diagnosis",
		)
		self.assertEqual(
			frappe.db.get_value("Livestock Event Type", "Health Case", "detail_doctype"),
			"Livestock Health Case",
		)

	def test_seeds_types_found_only_in_existing_data(self):
		frappe.db.delete("Livestock Event Type", {"name": "Hoof Trimming"})
		frappe.get_doc(
			{"doctype": "Livestock Event Type", "__newname": "Hoof Trimming", "is_active": 1}
		).insert()
		ensure_livestock_event_types()
		self.assertTrue(frappe.db.exists("Livestock Event Type", "Hoof Trimming"))

	def test_is_idempotent(self):
		ensure_livestock_event_types()
		before = frappe.db.count("Livestock Event Type")
		ensure_livestock_event_types()
		self.assertEqual(frappe.db.count("Livestock Event Type"), before)
