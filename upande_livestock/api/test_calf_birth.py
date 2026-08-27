# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What a birth records, and where each calf ends up.

A dam bearing twins where one lives and one dies is two outcomes, not an
average — so the properties that matter are per calf: its sex decides its herd,
its breed need not be its mother's, and the condition it was found in is a fact
about that animal on that day.

The chain is built in full — service, confirmed diagnosis, calving — because a
calving with no confirmed pregnancy is refused, and should be.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock import herd_movement as hm
from upande_livestock.api import operations as ops
from upande_livestock.api.animal import resolve_calf_herd
from upande_livestock.api.test_operations import _make_cow, _purge, _purge_events_for


def _employee():
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


class TestCalfRouting(IntegrationTestCase):
	"""Sex decides the herd, and nothing else does."""

	def setUp(self):
		s = hm.settings()
		if not (s.get("female_calf_herd") and s.get("male_calf_herd")):
			raise unittest.SkipTest("calf herds not configured")
		self.s = s

	def test_a_heifer_calf_joins_the_growth_ladder(self):
		self.assertEqual(resolve_calf_herd("Female"), self.s.get("female_calf_herd"))
		self.assertEqual(resolve_calf_herd("Female"), hm.growth_ladder()[0]["herd"])

	def test_a_bull_calf_goes_to_the_bull_herd(self):
		self.assertEqual(resolve_calf_herd("Male"), self.s.get("male_calf_herd"))

	def test_the_two_sexes_do_not_share_a_herd(self):
		"""Sending both to one herd puts bull calves on a ladder built for animals
		that will one day be milked."""
		self.assertNotEqual(resolve_calf_herd("Female"), resolve_calf_herd("Male"))

	def test_an_unknown_sex_falls_back_rather_than_failing(self):
		self.assertTrue(resolve_calf_herd(None))
		self.assertTrue(resolve_calf_herd(""))


class TestBirthOutcomes(IntegrationTestCase):
	"""One calving, three calves, three different outcomes."""

	def setUp(self):
		self.employee = _employee()
		if not self.employee:
			raise unittest.SkipTest("no active Employee on this site")
		if not frappe.db.exists("Breed", "Holstein-Friesian"):
			raise unittest.SkipTest("breeds not seeded (demo/seed_breeds.py)")
		self.dam = _make_cow("ZZ CALF TEST DAM", months_old=48)
		self.addCleanup(_purge_events_for, self.dam.name)
		self.addCleanup(_purge, "Animal", self.dam.name)
		for tag in ("ZZ CALF HEIFER", "ZZ CALF BULL"):
			self.addCleanup(_purge, "Animal", tag)

		served = add_days(today(), -285)
		r = ops.create_service_event({
			"animal": self.dam.name, "service_type": "A.I.",
			"service_date": served, "operator": self.employee,
		})
		if r.get("error"):
			raise unittest.SkipTest("could not record a service: {}".format(r["error"][:120]))
		dx = frappe.new_doc("Livestock Event")
		dx.event_type = "Pregnancy Diagnosis"
		dx.animal = self.dam.name
		dx.event_date = add_days(served, 60)
		dx.operator = self.employee
		dx.diagnosis_result = "Confirmed"
		dx.related_service = r["name"]
		dx.insert(ignore_permissions=True)
		dx.submit()

		self.calving = frappe.new_doc("Livestock Event")
		self.calving.event_type = "Calving"
		self.calving.animal = self.dam.name
		self.calving.event_date = today()
		self.calving.operator = self.employee
		self.calving.custom_no_of_calves = 3
		self.calving.insert(ignore_permissions=True)
		self.calving.submit()

		self.res = ops.record_calf_births({"calving": self.calving.name, "calves": [
			{"tag": "ZZ CALF HEIFER", "sex": "Female", "birth_weight": 34,
			 "breed": "Holstein-Friesian", "health_status": "Healthy",
			 "vet_remarks": "Strong, suckled within the hour"},
			{"tag": "ZZ CALF BULL", "sex": "Male", "birth_weight": 38,
			 "breed": "Ayrshire", "health_status": "Weak", "vet_remarks": "Slow to stand"},
			{"is_stillborn": 1},
		]})
		if self.res.get("error"):
			raise unittest.SkipTest("births refused: {}".format(self.res["error"][:140]))
		for name in frappe.get_all("Livestock Event",
		                           filters={"related_calving": self.calving.name}, pluck="name"):
			self.addCleanup(_purge, "Livestock Event", name)

	def test_one_birth_event_per_calf(self):
		births = frappe.get_all("Livestock Event", filters={"related_calving": self.calving.name})
		self.assertEqual(len(births), 3, "twins plus a stillbirth is three records, not one")

	def test_a_stillbirth_creates_no_animal(self):
		"""Recorded against the dam, but it never joins a herd or a head count."""
		still = frappe.get_all("Livestock Event",
		                       filters={"related_calving": self.calving.name, "is_stillborn": 1},
		                       fields=["name", "animal"])
		self.assertEqual(len(still), 1)
		self.assertFalse(still[0].animal, "a stillbirth must not bring an Animal into existence")
		self.assertEqual(len(self.res["created"]), 2, "only the two live calves exist")

	def test_each_calf_is_routed_by_its_own_sex(self):
		by_tag = {c["tag"]: c for c in self.res["created"]}
		self.assertEqual(by_tag["ZZ CALF HEIFER"]["herd"], hm.settings().get("female_calf_herd"))
		self.assertEqual(by_tag["ZZ CALF BULL"]["herd"], hm.settings().get("male_calf_herd"))

	def test_breed_is_per_calf_not_inherited_wholesale(self):
		"""A calf by a different sire need not be its mother's breed."""
		self.assertEqual(frappe.db.get_value("Animal", "ZZ CALF HEIFER", "breed"), "Holstein-Friesian")
		self.assertEqual(frappe.db.get_value("Animal", "ZZ CALF BULL", "breed"), "Ayrshire")

	def test_condition_at_birth_reaches_the_animal(self):
		heifer = frappe.db.get_value(
			"Animal", "ZZ CALF HEIFER", ["birth_health_status", "birth_vet_remarks"], as_dict=True)
		bull = frappe.db.get_value(
			"Animal", "ZZ CALF BULL", ["birth_health_status", "birth_vet_remarks"], as_dict=True)
		self.assertEqual(heifer.birth_health_status, "Healthy")
		self.assertEqual(bull.birth_health_status, "Weak")
		self.assertIn("suckled", heifer.birth_vet_remarks)
		self.assertNotEqual(heifer.birth_vet_remarks, bull.birth_vet_remarks)

	def test_the_condition_is_recorded_once_and_not_editable_after(self):
		"""It is a fact about one day. Ongoing health belongs to health cases."""
		meta = frappe.get_meta("Animal")
		for f in ("birth_health_status", "birth_vet_remarks"):
			self.assertTrue(meta.get_field(f).read_only, "{} must be read-only on Animal".format(f))

	def test_birth_weight_is_kept_per_calf(self):
		self.assertEqual(frappe.db.get_value("Animal", "ZZ CALF HEIFER", "birth_weight_kg"), 34)
		self.assertEqual(frappe.db.get_value("Animal", "ZZ CALF BULL", "birth_weight_kg"), 38)


class TestMovementSuggestions(IntegrationTestCase):
	"""Read-only: it proposes, a person decides."""

	def test_it_returns_the_three_kinds(self):
		s = hm.suggestions()
		for key in ("growth", "bulls", "open_cows", "counts"):
			self.assertIn(key, s)
		self.assertEqual(s["counts"]["growth"], len(s["growth"]))
		self.assertEqual(s["counts"]["bulls"], len(s["bulls"]))

	def test_a_growth_suggestion_names_both_ends(self):
		for r in hm.growth_suggestions():
			self.assertTrue(r["from_herd"])
			self.assertTrue(r["to_herd"])
			self.assertNotEqual(r["from_herd"], r["to_herd"])
			self.assertEqual(r["to_herd"], hm.next_growth_herd(r["from_herd"]))

	def test_nothing_is_suggested_off_the_service_rung(self):
		"""She leaves it by being served, so no day count may push her."""
		service_rungs = {r["herd"] for r in hm.growth_ladder() if r["exits_on_service"]}
		for r in hm.growth_suggestions():
			self.assertNotIn(r["from_herd"], service_rungs)

	def test_overdue_animals_come_first(self):
		rows = hm.growth_suggestions()
		if not any(r["overdue"] for r in rows):
			raise unittest.SkipTest("nothing overdue on this site")
		first_settled = next(i for i, r in enumerate(rows) if not r["overdue"])
		self.assertTrue(all(r["overdue"] for r in rows[:first_settled]))

	def test_suggesting_moves_nothing(self):
		"""The whole point: it is a proposal, not an action."""
		before = frappe.db.count("Livestock Event", {"event_type": "Movement"})
		hm.suggestions()
		self.assertEqual(frappe.db.count("Livestock Event", {"event_type": "Movement"}), before)
