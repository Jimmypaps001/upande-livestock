# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""animal_list and animal_profile carry what picks an animal's face: thumb and species."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.animals.animal_list import animal_list
from upande_livestock.serverscripts.animals.animal_profile import animal_profile
from upande_livestock.serverscripts.tests.test_animal import make_dam


class TestAnimalFace(IntegrationTestCase):
	def setUp(self):
		self.a = make_dam("TEST-FACE-A")

	def tearDown(self):
		if frappe.db.exists("Animal", "TEST-FACE-A"):
			frappe.delete_doc("Animal", "TEST-FACE-A", force=True, ignore_permissions=True)

	def test_list_rows_carry_thumb_and_species(self):
		row = next(x for x in animal_list()["animals"] if x["id"] == self.a.name)
		self.assertIn("thumb", row)
		self.assertIn("species", row)
		self.assertIsNone(row["thumb"])  # no photo, so no thumbnail

	def test_profile_carries_thumb_and_species(self):
		p = animal_profile({"animal": self.a.name})
		self.assertIn("thumb", p)
		self.assertIn("species", p)
