# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""animal_family: parents, offspring (disposed ones too) and a bull's record as sire."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.animals.animal_family import animal_family


def _animal(tag, sex, **extra):
	if frappe.db.exists("Animal", tag):
		frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
	return frappe.get_doc({
		"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": sex, "status": "Active",
		"breed": frappe.db.get_value("Breed", {}, "name"), **extra,
	}).insert(ignore_permissions=True)


class TestAnimalFamily(IntegrationTestCase):
	def setUp(self):
		self.made = []
		self.bull = self._make("ZZFAM-BULL", "Male")
		self.cow = self._make("ZZFAM-COW", "Female")

	def _make(self, tag, sex, **extra):
		a = _animal(tag, sex, **extra)
		self.made.append(a.name)
		return a

	def tearDown(self):
		for n in reversed(self.made):
			if frappe.db.exists("Animal", n):
				frappe.delete_doc("Animal", n, force=True, ignore_permissions=True)

	def test_parents_and_offspring_with_disposed(self):
		son = self._make("ZZFAM-SON", "Male", dam=self.cow.name, sire_name=self.bull.name,
		                 date_of_birth=add_days(today(), -100))
		daughter = self._make("ZZFAM-DAU", "Female", dam=self.cow.name, sire_name=self.bull.name,
		                      date_of_birth=add_days(today(), -400))
		sold = self._make("ZZFAM-SOLD", "Female", dam=self.cow.name, date_of_birth=add_days(today(), -800))
		frappe.db.set_value("Animal", sold.name, "status", "Sold")

		mum = animal_family({"animal": self.cow.name})
		self.assertTrue(mum["ok"], mum)
		self.assertEqual([o["id"] for o in mum["offspring"]], [son.name, daughter.name, sold.name])
		self.assertEqual((mum["sons"], mum["daughters"]), (1, 2))
		by = {o["id"]: o for o in mum["offspring"]}
		self.assertFalse(by[sold.name]["active"])
		self.assertEqual(by[sold.name]["status"], "Sold")
		self.assertTrue(by[son.name]["active"])
		self.assertIsNone(mum["bred"])

		calf = animal_family({"animal": son.name})
		self.assertEqual(calf["parents"]["dam"]["id"], self.cow.name)
		self.assertEqual(calf["parents"]["sire"]["id"], self.bull.name)
		self.assertEqual(calf["offspring"], [])

		dad = animal_family({"animal": self.bull.name})
		self.assertEqual({o["id"] for o in dad["offspring"]}, {son.name, daughter.name})

	def test_sire_written_by_name_only(self):
		ai = self._make("ZZFAM-AI", "Female", sire_name="ZZ AI Straw Bull")
		sire = animal_family({"animal": ai.name})["parents"]["sire"]
		self.assertEqual((sire["id"], sire["name"], sire["onRecord"]), (None, "ZZ AI Straw Bull", False))

	def test_unknown_animal_and_blank_are_refused(self):
		self.assertIn("error", animal_family({"animal": ""}))
		self.assertIn("error", animal_family({"animal": "ZZFAM-NOBODY"}))
