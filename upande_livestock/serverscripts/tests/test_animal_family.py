# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""animal_family: parents, offspring (disposed ones too) and a bull's record as sire."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.animals.animal_family import animal_family
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd


def _event(animal, event_type, days_ago, **extra):
	doc = frappe.get_doc({
		"doctype": "Livestock Event", "animal": animal, "event_type": event_type,
		"event_date": add_days(today(), -days_ago), "docstatus": 1, **extra,
	})
	doc.name = "ZZFAM-" + frappe.generate_hash(length=10)
	doc.db_insert()
	return doc


class TestAnimalFamily(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.herd = make_herd("ZZ Family", "Breeding").name
		self.bull = make_animal(self.herd, sex="Male", stream="Breeding")
		self.cow = make_animal(self.herd, sex="Female")
		self.cow2 = make_animal(self.herd, sex="Female")

	def test_parents_and_offspring_with_disposed(self):
		son = make_animal(self.herd, sex="Male", dam=self.cow.name, sire=self.bull.name,
		                  date_of_birth=add_days(today(), -100))
		daughter = make_animal(self.herd, sex="Female", dam=self.cow.name, sire=self.bull.name,
		                       date_of_birth=add_days(today(), -400))
		sold = make_animal(self.herd, sex="Male", dam=self.cow.name, date_of_birth=add_days(today(), -800))
		frappe.db.set_value("Animal", sold.name, "status", "Sold")

		mum = animal_family({"animal": self.cow.name})
		self.assertTrue(mum["ok"], mum)
		self.assertEqual([o["id"] for o in mum["offspring"]], [son.name, daughter.name, sold.name])
		self.assertEqual((mum["sons"], mum["daughters"]), (2, 1))
		by = {o["id"]: o for o in mum["offspring"]}
		self.assertFalse(by[sold.name]["active"])
		self.assertEqual(by[sold.name]["status"], "Sold")
		self.assertTrue(by[son.name]["active"])
		self.assertIsNone(mum["bred"])
		self.assertFalse(mum["breedingBull"])

		calf = animal_family({"animal": son.name})
		self.assertEqual(calf["parents"]["dam"]["id"], self.cow.name)
		self.assertEqual(calf["parents"]["sire"]["id"], self.bull.name)
		self.assertEqual(calf["offspring"], [])

		dad = animal_family({"animal": self.bull.name})
		self.assertEqual({o["id"] for o in dad["offspring"]}, {son.name, daughter.name})
		self.assertEqual((dad["sons"], dad["daughters"]), (1, 1))

	def test_sire_written_by_name_only(self):
		calf = make_animal(self.herd, sex="Female", sire_name=self.bull.burn_name)
		self.assertEqual(animal_family({"animal": calf.name})["parents"]["sire"]["id"], self.bull.name)
		self.assertIn(calf.name, [o["id"] for o in animal_family({"animal": self.bull.name})["offspring"]])
		ai = make_animal(self.herd, sex="Female", sire_name="ZZ AI Straw Bull")
		sire = animal_family({"animal": ai.name})["parents"]["sire"]
		self.assertEqual((sire["id"], sire["name"], sire["onRecord"]), (None, "ZZ AI Straw Bull", False))

	def test_bull_record_as_sire(self):
		_event(self.cow.name, "Service", 90, service_type="Natural", sire_animal=self.bull.name)
		_event(self.cow.name, "Service", 60, service_type="Natural", sire_animal=self.bull.name)
		_event(self.cow2.name, "Service", 30, service_type="Natural", sire_animal=self.bull.name)
		_event(self.cow.name, "Pregnancy Diagnosis", 20, diagnosis_result="Confirmed",
		       sire_animal=self.bull.name)
		bred = animal_family({"animal": self.bull.name})["bred"]
		self.assertEqual((bred["cows"], bred["services"], bred["conceptions"]), (2, 3, 1))
		self.assertEqual(bred["lastService"], str(add_days(today(), -30)))
		self.assertEqual(bred["conceptionRate"], 33)

	def test_unused_male_is_not_a_breeder(self):
		feedlot = make_herd("ZZ Family Feedlot", "Fattening").name
		steer = make_animal(feedlot, sex="Male")
		got = animal_family({"animal": steer.name})
		self.assertFalse(got["breedingBull"])
		self.assertEqual(got["bred"]["cows"], 0)
		self.assertIsNone(got["bred"]["conceptionRate"])
		self.assertTrue(animal_family({"animal": self.bull.name})["breedingBull"])
