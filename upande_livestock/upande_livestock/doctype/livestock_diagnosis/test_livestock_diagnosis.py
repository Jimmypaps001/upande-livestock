# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

# This site has no standard ERPNext test fixtures (e.g. "All Departments"), so
# following the dependency graph into Herds -> BOM -> Item -> Department blows up.
# Livestock Diagnosis's own test_livestock_event.py sibling hit the same wall;
# mirror its fix and build the fixtures we need by hand in setUp instead.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Animal",
	"Herds",
	"Company",
	"Employee",
	"Livestock Disease",
	"Livestock Health Case",
	# `stock_entry` was the one link left out, and it is the one that hurts:
	# following it imports erpnext's own test_stock_entry module, whose
	# module-level bootstrap wants the "All Departments" fixture this site does
	# not have. Everything Stock Entry drags in behind it is listed too, the
	# same way test_livestock_event.py does. No test below touches any of them.
	"Livestock Drug Issue",
	"Stock Entry",
	"Stock Entry Type",
	"Item",
	"Warehouse",
	"Account",
	"Cost Center",
	"Department",
]


def make_disease():
	name = "Test Mastitis"
	if frappe.db.exists("Livestock Disease", name):
		return frappe.get_doc("Livestock Disease", name)
	doc = frappe.get_doc(
		{
			"doctype": "Livestock Disease",
			"disease_name": name,
			"category": "Infectious - Bacterial",
			"typical_symptoms": "Swollen quarter, clots in milk",
			"typical_severity": "Moderate",
			"standard_protocol": "Intramammary antibiotic, 3 days",
			"expected_milk_withdrawal_days": 4,
			"is_zoonotic": 0,
			"is_notifiable": 1,
			"is_active": 1,
		}
	).insert()
	frappe.db.commit()
	return doc


class TestLivestockDiagnosisDiseaseReference(IntegrationTestCase):
	def setUp(self):
		self.disease = make_disease()
		self.addCleanup(self._cleanup_disease)

		# Operator is a mandatory Employee link on Livestock Diagnosis. Reuse an
		# existing Employee rather than creating one — this site's Employee
		# doctype has its own mandatory dependencies we don't need to satisfy.
		self.employee = frappe.db.get_value("Employee", {}, "name")

		if frappe.db.exists("Animal", "TEST-DX-1"):
			self.animal = frappe.get_doc("Animal", "TEST-DX-1")
		else:
			self.animal = frappe.get_doc(
				{
					"doctype": "Animal",
					"tag_number": "TEST-DX-1",
					"burn_name": "TEST-DX-1",
					"sex": "Female",
					"status": "Active",
				}
			).insert()
			frappe.db.commit()
			self.addCleanup(self._cleanup_animal)

	def _cleanup_disease(self):
		frappe.delete_doc("Livestock Disease", self.disease.name, force=True)
		frappe.db.commit()

	def _cleanup_animal(self):
		frappe.delete_doc("Animal", self.animal.name, force=True)
		frappe.db.commit()

	def test_old_fieldname_is_gone(self):
		self.assertIsNone(frappe.get_meta("Livestock Diagnosis").get_field("suggested_diagnosis"))

	def test_suggested_disease_links_livestock_disease(self):
		field = frappe.get_meta("Livestock Diagnosis").get_field("suggested_disease")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Livestock Disease")

	def test_selecting_a_disease_fetches_the_clinical_profile(self):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Diagnosis",
				"animal": self.animal.name,
				"diagnosis_date": "2026-04-01",
				"operator": self.employee,
				"action_taken": "No action — normal",
				"suggested_disease": self.disease.name,
			}
		).insert()
		self.addCleanup(
			lambda: (frappe.delete_doc("Livestock Diagnosis", doc.name, force=True), frappe.db.commit())
		)
		self.assertEqual(doc.disease_typical_symptoms, "Swollen quarter, clots in milk")
		self.assertEqual(doc.disease_typical_severity, "Moderate")
		self.assertEqual(doc.disease_standard_protocol, "Intramammary antibiotic, 3 days")
		self.assertEqual(doc.disease_milk_withdrawal_days, 4)
		self.assertEqual(doc.disease_is_zoonotic, 0)
		self.assertEqual(doc.disease_is_notifiable, 1)

	def test_fetched_fields_are_read_only(self):
		meta = frappe.get_meta("Livestock Diagnosis")
		for fieldname in (
			"disease_typical_symptoms",
			"disease_typical_severity",
			"disease_standard_protocol",
			"disease_milk_withdrawal_days",
			"disease_is_zoonotic",
			"disease_is_notifiable",
		):
			self.assertTrue(meta.get_field(fieldname).read_only, f"{fieldname} is editable")
