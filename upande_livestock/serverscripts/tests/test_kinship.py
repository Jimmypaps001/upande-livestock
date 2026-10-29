# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Relations: parents and siblings, full and half. Unknown parents never match."""

from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import kinship
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd


def born(days):
	return add_days(today(), -days)


class TestKinship(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.herd = make_herd("ZZ Kin Mating", "Breeding").name
		self.cow = make_animal(self.herd, sex="Female", date_of_birth=born(2500))
		self.cow2 = make_animal(self.herd, sex="Female", date_of_birth=born(2500))
		self.bull = make_animal(self.herd, sex="Male", date_of_birth=born(1500))
		self.bull2 = make_animal(self.herd, sex="Male", date_of_birth=born(1500))

	def _rel(self, a, b):
		found = kinship.relation(a.name, b.name)
		return found and found["relation"]

	def test_sire_daughter(self):
		daughter = make_animal(self.herd, sex="Female", date_of_birth=born(600), sire=self.bull.name)
		self.assertEqual(self._rel(self.bull, daughter), "sire-daughter")
		self.assertEqual(self._rel(daughter, self.bull), "sire-daughter")
		self.assertEqual(kinship.relation(self.bull.name, daughter.name)["shared_parent"], self.bull.name)

	def test_dam_son(self):
		son = make_animal(self.herd, sex="Male", date_of_birth=born(600), dam=self.cow.name)
		self.assertEqual(self._rel(son, self.cow), "dam-son")
		self.assertEqual(kinship.relation(son.name, self.cow.name)["shared_parent"], self.cow.name)

	def test_full_siblings(self):
		bro = make_animal(self.herd, sex="Male", date_of_birth=born(700), dam=self.cow.name, sire=self.bull.name)
		sis = make_animal(self.herd, sex="Female", date_of_birth=born(600), dam=self.cow.name, sire=self.bull.name)
		self.assertEqual(self._rel(bro, sis), "full-siblings")

	def test_half_siblings_name_the_shared_parent(self):
		bro = make_animal(self.herd, sex="Male", date_of_birth=born(700), dam=self.cow.name, sire=self.bull.name)
		by_dam = make_animal(self.herd, sex="Female", date_of_birth=born(600), dam=self.cow.name, sire=self.bull2.name)
		by_sire = make_animal(self.herd, sex="Female", date_of_birth=born(600), dam=self.cow2.name, sire=self.bull.name)
		a = kinship.relation(bro.name, by_dam.name)
		self.assertEqual((a["relation"], a["shared_parent"]), ("half-siblings", self.cow.name))
		b = kinship.relation(bro.name, by_sire.name)
		self.assertEqual((b["relation"], b["shared_parent"]), ("half-siblings", self.bull.name))
		self.assertIn("both sired by " + self.bull.name, b["message"])
		self.assertIn("half-siblings", b["message"])

	def test_unknown_parents_never_match(self):
		x = make_animal(self.herd, sex="Male", date_of_birth=born(700))
		y = make_animal(self.herd, sex="Female", date_of_birth=born(700))
		self.assertIsNone(kinship.relation(x.name, y.name))
		# a straw name is free text and is not compared
		p = make_animal(self.herd, sex="Male", date_of_birth=born(700), sire_name="Mazira")
		q = make_animal(self.herd, sex="Female", date_of_birth=born(700), sire_name="Mazira")
		self.assertIsNone(kinship.relation(p.name, q.name))

	def test_same_sex_pair_is_not_a_mating(self):
		a = make_animal(self.herd, sex="Female", date_of_birth=born(700), dam=self.cow.name)
		b = make_animal(self.herd, sex="Female", date_of_birth=born(700), dam=self.cow.name)
		self.assertIsNone(kinship.relation(a.name, b.name))

	def test_conflicts_in_a_herd(self):
		daughter = make_animal(self.herd, sex="Female", date_of_birth=born(600), sire=self.bull.name)
		found = kinship.conflicts(self.bull.name, self.herd)
		self.assertEqual([(c["other"], c["relation"]) for c in found], [(daughter.name, "sire-daughter")])
		# from the female's side too
		self.assertEqual([c["other"] for c in kinship.conflicts(daughter.name, self.herd)], [self.bull.name])

	def test_calf_under_separation_age_is_not_a_mate(self):
		make_animal(self.herd, sex="Female", date_of_birth=born(100), sire=self.bull.name)  # a suckling heifer
		self.assertEqual(kinship.conflicts(self.bull.name, self.herd), [])

	def test_conflicts_on_a_past_date_use_who_was_there(self):
		daughter = make_animal(self.herd, sex="Female", date_of_birth=born(600), sire=self.bull.name)
		self.assertEqual(len(kinship.conflicts(self.bull.name, self.herd, on=today())), 1)
		# before she was born she was not in the herd
		self.assertEqual(kinship.conflicts(self.bull.name, self.herd, on=born(700)), [])
		self.assertTrue(daughter)

	def test_herd_conflicts_lists_pairs(self):
		daughter = make_animal(self.herd, sex="Female", date_of_birth=born(600), sire=self.bull.name)
		pairs = kinship.herd_conflicts(self.herd)
		self.assertEqual([(p["male"], p["female"], p["relation"]) for p in pairs],
		                 [(self.bull.name, daughter.name, "sire-daughter")])
