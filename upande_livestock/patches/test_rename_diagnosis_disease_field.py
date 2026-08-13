# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Drive the patch against a throwaway diagnosis row.

suggested_disease already exists as a live column and DocType field once the
JSON has been synced, alongside the orphaned suggested_diagnosis column that
Frappe never drops. Asserting "the field is renamed" against DocType meta is a
schema check, not a data-migration check: it passes even if execute() were
`pass`, since model sync alone adds the new field. These tests instead put a
value directly into the orphaned old column via raw SQL (simulating a
not-yet-migrated row) and confirm execute() copies it across, so a stubbed
execute() fails.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.rename_diagnosis_disease_field import execute


def make_animal(tag):
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
	).insert()


class TestRenameDiagnosisDiseaseField(IntegrationTestCase):
	def setUp(self):
		self.animal = make_animal("TEST-DXPATCH-1").name
		self.addCleanup(self._purge_animal)
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def _purge_animal(self):
		if frappe.db.exists("Animal", self.animal):
			frappe.delete_doc("Animal", self.animal, force=True, ignore_permissions=True)
			frappe.db.commit()

	def _unmigrated_row(self, old_value):
		"""A diagnosis row with a value stuck in the orphaned old column only."""
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Diagnosis",
				"animal": self.animal,
				"diagnosis_date": "2026-04-01",
				"operator": self.operator,
				"action_taken": "No action — normal",
			}
		)
		doc.insert()
		self.addCleanup(self._purge, doc.name)
		frappe.db.sql(
			"""UPDATE `tabLivestock Diagnosis`
			   SET suggested_diagnosis = %(value)s, suggested_disease = NULL
			   WHERE name = %(name)s""",
			{"value": old_value, "name": doc.name},
		)
		frappe.db.commit()
		return doc.name

	def _purge(self, name):
		frappe.delete_doc("Livestock Diagnosis", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _suggested_disease(self, name):
		return frappe.db.get_value("Livestock Diagnosis", name, "suggested_disease")

	def test_execute_copies_the_orphaned_value_across(self):
		name = self._unmigrated_row("Mastitis")
		self.assertIsNone(self._suggested_disease(name))
		execute()
		self.assertEqual(self._suggested_disease(name), "Mastitis")

	def test_execute_is_idempotent(self):
		name = self._unmigrated_row("Foot Rot")
		execute()
		execute()
		self.assertEqual(self._suggested_disease(name), "Foot Rot")
